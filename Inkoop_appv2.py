import pandas as pd
from ortools.linear_solver import pywraplp
import streamlit as st

# Stijl aanpassen
st.markdown(
    """
    <style>
    body {
        background-color: #000; /* Zwarte achtergrond */
        color: white; /* Witte tekst */
        font-family: Arial, sans-serif; /* Modern sans-serif font */
    }
    .stButton>button {
        background-color: #008CBA; /* Lichte blauwe knoppenkleur */
        color: white;
        font-size: 16px;
        border-radius: 5px;
        padding: 10px;
    }
    .stTextInput>div>div>input {
        background-color: #333; /* Donkere invoervelden */
        color: white;
    }
    .stDataFrame {
        background-color: #111; /* Zwarte achtergrond voor tabellen */
        color: white;
        border: 2px solid #555; /* Grijze kaders om tabellen */
    }
    h1, h2, h3 {
        color: #fff; /* Witte koppen */
        font-weight: bold;
    }
    .stContainer {
        border: 2px solid #555;
        padding: 15px;
        border-radius: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Voeg logo toe (zorg ervoor dat je het juiste bestandspad hebt voor het logo)
st.image("vandaglas_logo.jpg", width=300)

st.title('Kosten Optimalisatie')

# Standaard dataset (laatste beschikbare data)
default_data = {
    'AGC': [144, 98, 50], 
    'Pilkington': [142, 99, 43], 
    'Saint Gobain': [155, 111, 100]
}
article_names = ['Monoperform 4mm', 'Monoperform 5mm', 'Protectperform 33/1']
supplier_names = ['AGC', 'Pilkington', 'Saint Gobain']
default_costs_df = pd.DataFrame(default_data, index=article_names)

# Excel uploadfunctie voor prijzen per leverancier en artikel (optioneel)
uploaded_file = st.file_uploader("Upload een Excel-bestand met prijzen (optioneel)", type=["xlsx"])

if uploaded_file:
    # Als een Excel-bestand wordt geüpload, laad de gegevens
    excel_data = pd.read_excel(uploaded_file, sheet_name="Sheet1")
    st.write("Ingelezen prijzen uit Excel:")
    st.dataframe(excel_data)
    # Gebruik de data uit het Excel-bestand
    costs_df = pd.DataFrame(excel_data.values, columns=supplier_names, index=article_names)
else:
    # Als er geen bestand wordt geüpload, gebruik de standaard data
    st.write("Gebruik standaard prijzen (laatste beschikbare data):")
    costs_df = default_costs_df.copy()
    st.dataframe(costs_df)

# Titel voor de invoerbare kosten tabel
st.write("**Vul de kosten per leverancier en artikel in (geüpdatet uit Excel of standaard):**")

# Visuele tabelstructuur opzetten voor de invoerbare kosten met vraagparameters als extra kolom
cols = st.columns([1.5, 1, 1, 1, 1])  # Artikelnaamkolom 50% breder
cols[0].markdown("**Artikel**")  # Vetgedrukte artikelnaam
for i, supplier in enumerate(supplier_names):
    cols[i+1].markdown(f"**{supplier}**")  # Vetgedrukte leveranciernaam
cols[4].markdown("**Vraag**")  # Extra kolom voor de vraagparameter

# Maak invoervelden in de "cellen" van de tabel inclusief vraagparameter rechts
questions = []
for article_idx, article in enumerate(article_names):
    cols = st.columns([1.5, 1, 1, 1, 1])  # Zelfde structuur, bredere artikelkolom
    cols[0].markdown(f"**{article}**")  # Vetgedrukte artikelnaam
    
    for i, supplier in enumerate(supplier_names):
        # In elke "cel" komt een number_input voor het invoeren van de kosten
        costs_df.loc[article, supplier] = cols[i+1].number_input(f'', 
                                                                 min_value=1, max_value=500, 
                                                                 value=int(costs_df.loc[article, supplier]))
    
    # Vraagparameter per artikel rechts van de tabel
    question = cols[4].number_input(f'', min_value=1, max_value=100, value=20 if article_idx == 0 else 15 if article_idx == 1 else 10)
    questions.append(question)

# Conversie van DataFrame naar lijst voor het optimalisatieprobleem
costs = costs_df.values.tolist()

# Invoervelden voor transportkosten, vrachtwagencapaciteit, en minimale bestelling bij Saint Gobain (standaard naar 0)
capacity = st.sidebar.number_input('Capaciteit per vrachtwagen', min_value=1, max_value=100, value=6)
transport_cost = st.sidebar.number_input('Transportkosten per rit', min_value=0, max_value=500, value=250)
min_order_supplier_3 = st.sidebar.number_input('Minimale bestelling bij Saint Gobain', min_value=0, max_value=100, value=0)

# Bereken de totale kosten per leverancier inclusief transportkosten
def calculate_costs_incl_transport(demands, quantity_matrix, costs_df, capacity, transport_cost):
    total_costs_per_supplier = {}
    total_articles_per_supplier = {}
    transport_per_supplier = {}
    for supplier in supplier_names:
        supplier_cost = 0
        total_units = 0
        for i, article in enumerate(article_names):
            total_units += quantity_matrix.loc[supplier, article]
            supplier_cost += quantity_matrix.loc[supplier, article] * costs_df.loc[article, supplier]
        
        # Bereken het aantal transporten
        if total_units > 0:  # Alleen transportkosten berekenen als er artikelen worden geleverd
            num_trips = (total_units // capacity) + (1 if total_units % capacity > 0 else 0)
        else:
            num_trips = 0
        supplier_cost += num_trips * transport_cost
        total_costs_per_supplier[supplier] = supplier_cost
        total_articles_per_supplier[supplier] = total_units
        transport_per_supplier[supplier] = num_trips

    return total_costs_per_supplier, total_articles_per_supplier, transport_per_supplier

# Functie om het transportprobleem op te lossen (na het berekenen van totale kosten)
def solve_transportation_problem(costs, transport_cost, demands, capacity, min_order_supplier_3):
    solver = pywraplp.Solver.CreateSolver('SCIP')
    num_articles = len(costs)
    num_suppliers = len(costs[0])

    x = {}
    for i in range(num_articles):
        for j in range(num_suppliers):
            x[i, j] = solver.IntVar(0, solver.infinity(), f'x[{i},{j}]')

    trucks = [solver.IntVar(0, solver.infinity(), f'trucks[{j}]') for j in range(num_suppliers)]

    objective_terms = []
    for i in range(num_articles):
        for j in range(num_suppliers):
            objective_terms.append(costs[i][j] * x[i, j])
    
    for j in range(num_suppliers):
        objective_terms.append(transport_cost * trucks[j])

    solver.Minimize(solver.Sum(objective_terms))

    # Beperkingen
    for j in range(num_suppliers):
        solver.Add(solver.Sum([x[i, j] for i in range(num_articles)]) <= trucks[j] * capacity)

    # Beperkingen voor vraag per artikel
    for i in range(num_articles):
        solver.Add(solver.Sum([x[i, j] for j in range(num_suppliers)]) == demands[i])
    
    # Minimale bestelling voor Saint Gobain
    solver.Add(solver.Sum([x[i, 2] for i in range(num_articles)]) >= min_order_supplier_3)

    status = solver.Solve()

    if status == pywraplp.Solver.OPTIMAL:
        quantity_matrix = pd.DataFrame(0, index=[supplier_names[j] for j in range(num_suppliers)], 
                                       columns=[article_names[i] for i in range(num_articles)])
        for i in range(num_articles):
            for j in range(num_suppliers):
                if x[i, j].solution_value() > 0:
                    quantity_matrix.loc[supplier_names[j], article_names[i]] = int(x[i, j].solution_value())

        return quantity_matrix
    else:
        return None

# Optimaliseer de bestelhoeveelheden
quantity_matrix = solve_transportation_problem(costs, transport_cost, questions, capacity, min_order_supplier_3)

# Bereken de geoptimaliseerde hoeveelheden en totale kosten met minimale bestelling op 0
quantity_matrix_no_min = solve_transportation_problem(costs, transport_cost, questions, capacity, 0)

# Totale kosten en transportkosten berekenen
if quantity_matrix is not None:
    total_costs_per_supplier, total_articles_per_supplier, transport_per_supplier = calculate_costs_incl_transport(questions, quantity_matrix, costs_df, capacity, transport_cost)
    total_cost_with_minimum = sum(total_costs_per_supplier.values())

    total_costs_no_minimum, _, _ = calculate_costs_incl_transport(questions, quantity_matrix_no_min, costs_df, capacity, transport_cost)
    total_cost_no_minimum = sum(total_costs_no_minimum.values())

    # Kostenverschil berekenen
    cost_difference = total_cost_with_minimum - total_cost_no_minimum

    # Resultaten tonen van de totale kosten inclusief transportkosten
    st.write("Totale kosten per leverancier, inclusief transportkosten:")
    total_costs_df = pd.DataFrame.from_dict(total_costs_per_supplier, orient='index', columns=['Totale Kosten'])

    # Aantal artikelen en transportritten toevoegen
    total_costs_df['Aantal Artikelen'] = pd.Series(total_articles_per_supplier).astype(int)
    total_costs_df['Aantal Transportritten'] = pd.Series(transport_per_supplier).astype(int)

    # Totale som toevoegen
    total_costs_df.loc['Totaal', 'Totale Kosten'] = total_costs_df['Totale Kosten'].sum()
    total_costs_df.loc['Totaal', 'Aantal Artikelen'] = total_costs_df['Aantal Artikelen'].sum()
    total_costs_df.loc['Totaal', 'Aantal Transportritten'] = total_costs_df['Aantal Transportritten'].sum()

    st.dataframe(total_costs_df.style.format({
        'Totale Kosten': '€ {:,.2f}',  # Toon 2 decimalen voor kosten
        'Aantal Artikelen': '{:.0f}',  # Geen decimalen voor aantal artikelen
        'Aantal Transportritten': '{:.0f}'  # Geen decimalen voor aantal transporten
    }))

    # Tabelweergave van geoptimaliseerde hoeveelheden
    st.write("Geoptimaliseerde bestelhoeveelheden per leverancier en artikel:")
    st.dataframe(quantity_matrix)

    # Kostenverschil tonen
    st.write(f"Verschil in totale kosten wanneer minimale bestelling bij Saint Gobain op 0 wordt gezet: € {cost_difference:.2f}")

else:
    st.write("Er is geen optimale oplossing gevonden.")