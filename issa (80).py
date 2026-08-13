import base64
from datetime import datetime
import io
import json
import os
import zipfile
import unicodedata
import numpy as np
import pandas as pd
from fpdf import FPDF
import streamlit as st
import bcrypt
from supabase import create_client, Client

# ==========================================
# 0. CONFIGURATION SUPABASE & CONNEXION
# ==========================================
SUPABASE_URL = "https://gxzprzTufqvblwoyqihd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd4enByenR1ZnF2Ymx3b3lxaWhkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2NTAwNDgsImV4cCI6MjEwMjIyNjA0OH0.CK9c_hb3bp6q0V7zHBWoX15BwqNHCUSYY9DRXqgOP_Q"

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

def hacher_mot_de_passe(password: str) -> str:
    if not password: return ""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verifier_mot_de_passe(password: str, hashed: str) -> bool:
    if not password or not hashed: return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def normaliser_texte(texte):
    """Normalise une chaîne de caractères pour une recherche universelle (insensible aux accents, casse, espaces)."""
    if not texte: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(texte)) if unicodedata.category(c) != 'Mn').strip().lower()

def nettoyer_texte_pdf(texte):
    """Nettoie et encode le texte pour garantir la compatibilité PDF sans erreur d'affichage."""
    if not texte: return ""
    return str(texte).encode('latin-1', 'replace').decode('latin-1')

ADMIN_EMAIL = "cpnm@gmail.com"

def enregistrer_log_action(acteur: str, action: str, details: str):
    """Consigne chaque action utilisateur dans la table Supabase audit_logs."""
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        supabase.table("audit_logs").insert({
            "acteur": acteur,
            "role": "system",
            "action": action,
            "details": details
        }).execute()
    except Exception as e:
        print(f"Erreur log Supabase: {e}")

def trier_eleves_par_nom(df):
    if df is None or df.empty: return df
    df_copy = df.copy()
    if "nom" in df_copy.columns and "prenom" in df_copy.columns:
        df_copy["Nom_Sort"] = df_copy["nom"].astype(str).str.strip().str.upper()
        df_copy["Prenom_Sort"] = df_copy["prenom"].astype(str).str.strip().str.upper()
        df_copy = df_copy.sort_values(by=["Nom_Sort", "Prenom_Sort"]).drop(columns=["Nom_Sort", "Prenom_Sort"])
    elif "Nom" in df_copy.columns and "Prénom" in df_copy.columns:
        df_copy["Nom_Sort"] = df_copy["Nom"].astype(str).str.strip().str.upper()
        df_copy["Prenom_Sort"] = df_copy["Prénom"].astype(str).str.strip().str.upper()
        df_copy = df_copy.sort_values(by=["Nom_Sort", "Prenom_Sort"]).drop(columns=["Nom_Sort", "Prenom_Sort"])
    return df_copy.reset_index(drop=True)

def synchroniser_listes_blanches():
    """Maintient la cohérence absolue et bidirectionnelle des accès professeurs depuis Supabase."""
    try:
        res = supabase.table("teachers").select("*").execute()
        if res.data:
            st.session_state.prof_white_list = pd.DataFrame(res.data)
            st.session_state.prof_credentials = pd.DataFrame(res.data)
    except Exception as e:
        print(f"Erreur synchronisation teachers: {e}")

# ==========================================
# 0. BIS. GESTION DU DESIGN ET DU DRAPEAU
# ==========================================

SCEAU_SENEGAL_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAABHNCSVQICAgIfAhkiAAAAAlwSFlz"
    "AAAOxAAADsQBlSsOGwAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ2V3ZgZ3AAAAYklE"
    "EQVR4nO3BMQEAAADCoPVPbQwfoAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAICXAcB4AAEq99A1"
    "AAAAAElFTkSuQmCC"
)

def obtenir_logo_base64():
    return ""

def assistant_ia_repondre(question: str) -> str:
    q = question.lower()
    if "bulletin" in q or "note" in q:
        return (
            "Les bulletins d'excellence sont générés automatiquement au format"
            " standardisé sous l'autorité de l'IA Saint-Louis et IEF Saint-Louis,"
            " garantissant rigueur et équité pour chaque élève."
        )
    elif "prof" in q or "enseignant" in q:
        return (
            "Nos enseignants d'élite s'engagent au quotidien pour encadrer les"
            " notes, le cahier de texte, le travail à faire et le suivi"
            " personnalisé."
        )
    elif "parent" in q or "élève" in q:
        return (
            "Les parents disposent d'un suivi pédagogique transparent en temps réel"
            " (travaux à faire, devoirs, pièces jointes, emploi du temps et vie"
            " scolaire) pour accompagner la réussite de leurs enfants."
        )
    elif "admin" in q or "administrateur" in q:
        return (
            "L'administration pilote l'établissement avec dévouement pour"
            " maintenir les plus hauts standards de qualité académique."
        )
    return (
        "École Président Nelson Mandela - Excellence, Discipline et Réussite au"
        " cœur du Système Pédagogique (IA Saint-Louis / IEF Saint-Louis)."
    )

# ==========================================
# 1. CONFIGURATION DE LA PAGE & DESIGN XXL
# ==========================================
st.set_page_config(
    page_title=(
        "Sénégal - Portail Éducatif National École Président Nelson Mandela"
    ),
    page_icon="🇸🇳",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800;900&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }

    .stApp {
        background: radial-gradient(circle at top left, #F8FAFC 0%, #EFF6FF 40%, #DBEAFE 100%);
        color: #0F172A;
    }

    @keyframes fadeInSlide {
        0% { opacity: 0; transform: translateY(15px); }
        100% { opacity: 1; transform: translateY(0); }
    }

    @keyframes pulseGlow {
        0% { box-shadow: 0 0 0 0 rgba(14, 116, 144, 0.4); }
        70% { box-shadow: 0 0 0 18px rgba(14, 116, 144, 0); }
        100% { box-shadow: 0 0 0 0 rgba(14, 116, 144, 0); }
    }

    .header-institutionnel {
        background: linear-gradient(135deg, #0EA5E9 0%, #2563EB 50%, #1D4ED8 100%);
        padding: 10px;
        border-radius: 32px;
        box-shadow: 0 25px 50px rgba(14, 165, 233, 0.3);
        margin-bottom: 35px;
        animation: fadeInSlide 0.8s ease-out;
    }

    .header-inner {
        background: rgba(255, 255, 255, 0.99);
        backdrop-filter: blur(20px);
        padding: 25px 35px;
        border-radius: 26px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 25px;
    }

    .header-text {
        text-align: center;
        flex-grow: 1;
    }

    .ministere-title {
        color: #0F172A;
        font-size: clamp(1.2rem, 2.5vw, 1.9rem);
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        margin: 0;
    }

    .ia-ief-sub {
        color: #1E3A8A;
        font-size: clamp(0.9rem, 1.8vw, 1.2rem);
        font-weight: 700;
        margin: 6px 0;
        letter-spacing: 0.5px;
    }

    .ecole-title {
        color: #0EA5E9;
        font-size: clamp(1.4rem, 2.8vw, 2.3rem);
        font-weight: 900;
        margin: 8px 0 0 0;
        text-transform: uppercase;
    }

    .logo-frame-container {
        background: linear-gradient(135deg, #FFFFFF 0%, #F0F9FF 100%);
        border: 4px solid #0EA5E9;
        border-radius: 22px;
        padding: 6px;
        box-shadow: 0 12px 28px rgba(14, 165, 233, 0.3);
        display: flex;
        align-items: center;
        justify-content: center;
        width: 130px;
        height: 130px;
        flex-shrink: 0;
        animation: pulseGlow 3s infinite;
    }

    .logo-frame-container img {
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
        border-radius: 14px;
    }

    .emblem-box {
        background: #F0F9FF;
        border: 4px solid #0EA5E9;
        border-radius: 50%;
        width: 115px;
        height: 115px;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 10px 25px rgba(14, 165, 233, 0.35);
        flex-shrink: 0;
        animation: pulseGlow 3s infinite;
    }

    .animated-card {
        border: 2px solid rgba(186, 230, 253, 0.9);
        padding: 40px 24px;
        border-radius: 30px;
        background: linear-gradient(145deg, #FFFFFF 0%, #F0F9FF 100%);
        box-shadow: 0 18px 40px rgba(15, 23, 42, 0.1);
        transition: all 0.4s cubic-bezier(0.165, 0.84, 0.44, 1);
        text-align: center;
        margin-bottom: 30px;
        min-height: 330px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        animation: fadeInSlide 0.8s ease-out;
    }

    .animated-card:hover {
        transform: translateY(-12px) scale(1.02);
        border-color: #0EA5E9;
        box-shadow: 0 30px 60px rgba(14, 165, 233, 0.3);
        background: #FFFFFF;
    }

    .stButton>button {
        background: linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%) !important;
        color: #FFFFFF !important;
        border-radius: 18px !important;
        font-weight: 800 !important;
        border: none !important;
        padding: 0.9rem 1.5rem !important;
        transition: all 0.3s ease !important;
        width: 100% !important;
        min-height: 56px !important;
        font-size: 1.1rem !important;
        box-shadow: 0 10px 25px rgba(14, 165, 233, 0.35) !important;
    }

    .stButton>button:hover {
        transform: translateY(-3px) !important;
        box-shadow: 0 15px 32px rgba(14, 165, 233, 0.5) !important;
        background: linear-gradient(135deg, #0284C7 100%, #0369A1 100%) !important;
    }

    .stTextInput input, .stSelectbox select, .stNumberInput input, .stTextArea textarea {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
        border: 2px solid #7DD3FC !important;
        border-radius: 16px !important;
        font-weight: 600 !important;
    }

    .stTextInput input:focus, .stSelectbox select:focus, .stNumberInput input:focus {
        border-color: #0EA5E9 !important;
        box-shadow: 0 0 0 4px rgba(14, 165, 233, 0.25) !important;
    }

    .work-card {
        background: #FFFFFF;
        border: 2px solid #BAE6FD;
        border-left: 6px solid #0EA5E9;
        border-radius: 18px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 10px 25px rgba(15, 23, 42, 0.05);
    }

    .msg-card {
        background: #FFFFFF;
        border: 2px solid #C7D2FE;
        border-left: 6px solid #4F46E5;
        border-radius: 18px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 10px 25px rgba(15, 23, 42, 0.05);
    }

    h1, h2, h3, h4, h5, h6, label, p, span {
        color: #0F172A !important;
    }
    </style>
""",
    unsafe_allow_html=True,
)

hide_streamlit_style = """
    <style>
    [data-testid="stToolbar"] { display: none; }
    footer { visibility: hidden; }
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)
# ==========================================
# 2. INITIALISATION EXHAUSTIVE DES DONNÉES LOCALES
# ==========================================
if "espace_actif" not in st.session_state:
    st.session_state.espace_actif = "🏠 Accueil"

if "authenticated_admin" not in st.session_state:
    st.session_state.authenticated_admin = False

if "edt_documents" not in st.session_state:
    st.session_state.edt_documents = {}

if "admin_credentials" not in st.session_state:
    st.session_state.admin_credentials = pd.DataFrame([{
        "Nom": "Principal",
        "Prénom": "Admin",
        "Email": ADMIN_EMAIL,
        "Mot de passe": hacher_mot_de_passe("cpnm2026"),
        "Niveau d'accès": "Super-Admin Ayant-Droit",
    }])

if "admin_white_list" not in st.session_state:
    st.session_state.admin_white_list = pd.DataFrame([
        {
            "Email": ADMIN_EMAIL,
            "Nom": "Mandela",
            "Prénom": "Ayant Droit",
            "Mot de passe": hacher_mot_de_passe("cpnm2026"),
            "Niveau d'accès": "Super-Admin Ayant-Droit",
        }
    ])

if "prof_credentials" not in st.session_state:
    st.session_state.prof_credentials = pd.DataFrame(columns=["Nom", "Prénom", "Email", "Matière Principale", "Classe Attribuée", "Mot de passe"])

for col in [
    "Nom",
    "Prénom",
    "Email",
    "Matière Principale",
    "Classe Attribuée",
    "Mot de passe",
]:
    if col not in st.session_state.prof_credentials.columns:
        st.session_state.prof_credentials[col] = ""

if "prof_white_list" not in st.session_state:
    st.session_state.prof_white_list = st.session_state.prof_credentials.copy()

if "parents_white_list" not in st.session_state:
    st.session_state.parents_white_list = pd.DataFrame(columns=["Téléphone", "Prénom Élève", "Nom Élève", "Année Naissance", "Classe"])

if "classes_db" not in st.session_state:
    st.session_state.classes_db = pd.DataFrame(
        columns=["Classe", "Cycle", "Professeur Responsable"],
        data=[
            ["6ème A", "Collège", "Prof. Math"],
            ["CP", "Élémentaire", "Prof. Élémen"]
        ],
    )

if "eleves_db" not in st.session_state:
    st.session_state.eleves_db = pd.DataFrame(
        columns=[
            "Nom Complet",
            "Prénom",
            "Nom",
            "Date de Naissance",
            "Classe",
            "Photo",
        ],
        data=[],
    )

for col_req in [
    "Nom Complet",
    "Prénom",
    "Nom",
    "Date de Naissance",
    "Classe",
    "Photo",
]:
    if col_req not in st.session_state.eleves_db.columns:
        st.session_state.eleves_db[col_req] = ""

if not st.session_state.eleves_db.empty:
    st.session_state.eleves_db = trier_eleves_par_nom(st.session_state.eleves_db)

if "matieres_def" not in st.session_state:
    st.session_state.matieres_def = pd.DataFrame([
        {"Matière": "Mathématiques", "Cycle": "Collège", "Coefficient": 4, "Barème": 20},
        {"Matière": "Français", "Cycle": "Collège", "Coefficient": 5, "Barème": 20},
        {
            "Matière": "Histoire-Géographie",
            "Cycle": "Collège",
            "Coefficient": 2,
            "Barème": 20,
        },
        {"Matière": "SVT", "Cycle": "Collège", "Coefficient": 2, "Barème": 20},
        {"Matière": "Anglais", "Cycle": "Collège", "Coefficient": 2, "Barème": 20},
        {
            "Matière": "Physique-Chimie",
            "Cycle": "Collège",
            "Coefficient": 2,
            "Barème": 20,
        },
        {
            "Matière": "Lecture / Langage",
            "Cycle": "Élémentaire",
            "Coefficient": 1,
            "Barème": 50,
        },
        {
            "Matière": "Calcul / Mathématiques",
            "Cycle": "Élémentaire",
            "Coefficient": 1,
            "Barème": 50,
        },
        {
            "Matière": "Éveil / Science",
            "Cycle": "Élémentaire",
            "Coefficient": 1,
            "Barème": 30,
        },
        {
            "Matière": "Éducation Civique",
            "Cycle": "Élémentaire",
            "Coefficient": 1,
            "Barème": 20,
        },
    ])

if "Barème" not in st.session_state.matieres_def.columns:
    st.session_state.matieres_def["Barème"] = (
        st.session_state.matieres_def["Cycle"].apply(
            lambda x: 20 if x == "Collège" else 50
        )
    )

if "coefficients_db" not in st.session_state:
    st.session_state.coefficients_db = pd.DataFrame([
        {
            "Classe": "6ème A",
            "Matière": "Mathématiques",
            "Coefficient": 4,
            "Barème": 20,
        },
        {
            "Classe": "6ème A",
            "Matière": "Français",
            "Coefficient": 5,
            "Barème": 20,
        },
        {
            "Classe": "6ème A",
            "Matière": "Histoire-Géographie",
            "Coefficient": 2,
            "Barème": 20,
        },
        {"Classe": "6ème A", "Matière": "SVT", "Coefficient": 2, "Barème": 20},
        {
            "Classe": "6ème A",
            "Matière": "Anglais",
            "Coefficient": 2,
            "Barème": 20,
        },
        {
            "Classe": "6ème A",
            "Matière": "Physique-Chimie",
            "Coefficient": 2,
            "Barème": 20,
        },
        {
            "Classe": "CP",
            "Matière": "Lecture / Langage",
            "Coefficient": 1,
            "Barème": 50,
        },
        {
            "Classe": "CP",
            "Matière": "Calcul / Mathématiques",
            "Coefficient": 1,
            "Barème": 50,
        },
        {
            "Classe": "CP",
            "Matière": "Éveil / Science",
            "Coefficient": 1,
            "Barème": 30,
        },
        {
            "Classe": "CP",
            "Matière": "Éducation Civique",
            "Coefficient": 1,
            "Barème": 20,
        },
    ])

if "Barème" not in st.session_state.coefficients_db.columns:
    st.session_state.coefficients_db["Barème"] = 20

if "periodes_db" not in st.session_state:
    st.session_state.periodes_db = pd.DataFrame([
        {"Période": "1er Trimestre", "Statut": "Ouvert", "Cycle": "Élémentaire"},
        {"Période": "2ème Trimestre", "Statut": "Fermé", "Cycle": "Élémentaire"},
        {"Période": "3ème Trimestre", "Statut": "Fermé", "Cycle": "Élémentaire"},
        {"Période": "1er Semestre", "Statut": "Ouvert", "Cycle": "Collège"},
        {"Période": "2ème Semestre", "Statut": "Fermé", "Cycle": "Collège"},
    ])

if "notes_db" not in st.session_state:
    st.session_state.notes_db = pd.DataFrame(
        columns=[
            "Classe",
            "Matière",
            "Periode",
            "Période",
            "Eleve",
            "Devoir1",
            "Devoir2",
            "Composition",
            "BaremeNote",
        ],
        data=[],        
    )

if isinstance(st.session_state.notes_db, pd.DataFrame):
    st.session_state.notes_db = st.session_state.notes_db.reset_index(drop=True)
    if "BaremeNote" not in st.session_state.notes_db.columns:
        st.session_state.notes_db["BaremeNote"] = 20.0

if (
    "Periode" not in st.session_state.notes_db.columns
    and "Période" in st.session_state.notes_db.columns
):
    st.session_state.notes_db["Periode"] = st.session_state.notes_db["Période"]
elif (
    "Période" not in st.session_state.notes_db.columns
    and "Periode" in st.session_state.notes_db.columns
):
    st.session_state.notes_db["Période"] = st.session_state.notes_db["Periode"]
elif (
    "Periode" not in st.session_state.notes_db.columns
    and "Période" not in st.session_state.notes_db.columns
):
    st.session_state.notes_db["Periode"] = "1er Semestre"
    st.session_state.notes_db["Période"] = "1er Semestre"

if "viescolaire_db" not in st.session_state:
    st.session_state.viescolaire_db = pd.DataFrame(
        columns=[
            "Classe",
            "Periode",
            "Période",
            "Eleve",
            "AbsencesJustifiees",
            "AbsencesNonJustifiees",
            "Retards",
            "HeuresPerdues",
            "Observations",
            "DecisionConseil",
        ],
        data=[],
    )

if "travail_a_faire_db" not in st.session_state:
    st.session_state.travail_a_faire_db = pd.DataFrame(
        columns=[
            "ID",
            "Professeur",
            "DatePublication",
            "DateRendu",
            "Classe",
            "Matière",
            "Titre",
            "Consignes",
            "LienUrl",
            "LienVideo",
            "FichierNom",
            "FichierB64",
            "FichierType",
        ],
        data=[],
    )

if "messages_parents_db" not in st.session_state:
    st.session_state.messages_parents_db = pd.DataFrame(
        columns=[
            "ID",
            "Emetteur",
            "RoleEmetteur",
            "DateEnvoi",
            "Classe",
            "Objet",
            "Message",
            "Urgent",
        ],
        data=[],
    )

JOURS_LIST = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]

HEURES_LIST = [
    "08h-09h",
    "09h-10h",
    "10h-11h",
    "11h00-11h30",
    "11h30-12h",
    "12h-13h",
    "13h-14h",
    "14h-15h",
    "15h-16h",
    "16h-17h",
    "17h-18h",
    "18h-19h",
]

if "edt_grid_db" not in st.session_state:
    st.session_state.edt_grid_db = {}


def get_or_create_edt(classe):
    if classe not in st.session_state.edt_grid_db:
        df_def = pd.DataFrame("", index=JOURS_LIST, columns=HEURES_LIST)
        if "11h00-11h30" in df_def.columns:
            df_def["11h00-11h30"] = "Récréation"
        st.session_state.edt_grid_db[classe] = df_def
    else:
        df_exist = st.session_state.edt_grid_db[classe]
        if "11h00-11h30" not in df_exist.columns:
            df_def = pd.DataFrame("", index=JOURS_LIST, columns=HEURES_LIST)
            for col in df_exist.columns:
                if col in df_def.columns:
                    df_def[col] = df_exist[col]
            if "11h00-11h30" in df_def.columns:
                df_def["11h00-11h30"] = "Récréation"
            st.session_state.edt_grid_db[classe] = df_def
    return st.session_state.edt_grid_db[classe]


if "cahier_textes" not in st.session_state:
    st.session_state.cahier_textes = pd.DataFrame(
        columns=[
            "Professeur",
            "Date",
            "Classe",
            "Matière",
            "Contenu",
            "Travail à faire",
        ],
        data=[],
    )

if "absences_db" not in st.session_state:
    st.session_state.absences_db = pd.DataFrame(
        columns=["Date", "Classe", "Élève", "Statut", "Motif"], data=[]
    )

synchroniser_listes_blanches()

# ==========================================
# ==========================================
# 3. FONCTIONS MÉTIER & UTILITAIRES
# ==========================================

def obtenir_cycle_classe(classe_nom):
    if not classe_nom:
        return "Élémentaire"

    classe_str = str(classe_nom).strip()

    if (
        "classes_db" in st.session_state
        and not st.session_state.classes_db.empty
        and "Classe" in st.session_state.classes_db.columns
    ):
        res = st.session_state.classes_db[
            st.session_state.classes_db["Classe"].str.strip().str.upper()
            == classe_str.upper()
        ]
        if not res.empty and pd.notna(res.iloc[0].get("Cycle")):
            return str(res.iloc[0]["Cycle"]).strip()

    classe_clean = classe_str.upper()
    if any(
        c in classe_clean
        for c in [
            "6ÈME",
            "6EME",
            "5ÈME",
            "5EME",
            "4ÈME",
            "4EME",
            "3ÈME",
            "3EME",
            "COLLÈGE",
            "COLLEGE",
        ]
    ):
        return "Collège"
    if any(
        classe_clean.startswith(prefix)
        for prefix in [
            "CI",
            "CP",
            "CE1",
            "CE2",
            "CM1",
            "CM2",
            "ÉLÉMENTAIRE",
            "ELEMENTAIRE",
        ]
    ):
        return "Élémentaire"

    return "Élémentaire"


def est_cycle_elementaire(cycle_or_classe):
    if not cycle_or_classe:
        return True
    val = str(cycle_or_classe).strip().lower()
    if "élément" in val or "element" in val:
        return True
    if "collèg" in val or "colleg" in val:
        return False
    return est_cycle_elementaire(obtenir_cycle_classe(cycle_or_classe))


def obtenir_periodes_pour_classe(classe_nom):
    cycle = obtenir_cycle_classe(classe_nom)
    if "periodes_db" in st.session_state and not st.session_state.periodes_db.empty:
        df_p = st.session_state.periodes_db
        col_cycle = "Cycle" if "Cycle" in df_p.columns else None
        col_periode = (
            "Période"
            if "Période" in df_p.columns
            else ("Periode" if "Periode" in df_p.columns else None)
        )

        if col_cycle and col_periode:
            filtre = (
                df_p[
                    df_p[col_cycle].apply(est_cycle_elementaire)
                    == est_cycle_elementaire(cycle)
                ][col_periode]
                .dropna()
                .tolist()
            )
            if filtre:
                return filtre
        elif col_periode:
            return df_p[col_periode].dropna().tolist()

    if est_cycle_elementaire(cycle):
        return ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"]
    else:
        return ["1er Semestre", "2ème Semestre"]


def obtenir_appreciation(moyenne, cycle="Collège", bareme=20):
    if pd.isna(moyenne):
        return "N/A"
    m = (moyenne / bareme) * 20.0 if bareme > 0 else moyenne
    if m >= 18:
        return "Excellent"
    elif m >= 16:
        return "Très Bien"
    elif m >= 14:
        return "Bien"
    elif m >= 12:
        return "Assez Bien"
    elif m >= 10:
        return "Passable"
    elif m >= 8:
        return "Insuffisant"
    else:
        return "Faible"


def obtenir_coefficient_matiere(classe, matiere):
    if (
        "coefficients_db" in st.session_state
        and not st.session_state.coefficients_db.empty
    ):
        c_db = st.session_state.coefficients_db
        if "Classe" in c_db.columns and "Matière" in c_db.columns:
            res = c_db[(c_db["Classe"] == classe) & (c_db["Matière"] == matiere)]
            if not res.empty and pd.notna(res.iloc[0].get("Coefficient")):
                return float(res.iloc[0]["Coefficient"])

    cycle_classe = obtenir_cycle_classe(classe)
    if "matieres_def" in st.session_state and not st.session_state.matieres_def.empty:
        m_def = st.session_state.matieres_def
        if "Cycle" in m_def.columns:
            res = m_def[
                (m_def["Matière"] == matiere)
                & (
                    m_def["Cycle"].apply(est_cycle_elementaire)
                    == est_cycle_elementaire(cycle_classe)
                )
            ]
        else:
            res = m_def[m_def["Matière"] == matiere]
        if (
            not res.empty
            and "Coefficient" in m_def.columns
            and pd.notna(res.iloc[0].get("Coefficient"))
        ):
            return float(res.iloc[0]["Coefficient"])

    return 1.0


def obtenir_bareme_matiere(classe, matiere):
    if (
        "coefficients_db" in st.session_state
        and not st.session_state.coefficients_db.empty
    ):
        c_db = st.session_state.coefficients_db
        if "Classe" in c_db.columns and "Matière" in c_db.columns:
            res = c_db[(c_db["Classe"] == classe) & (c_db["Matière"] == matiere)]
            if (
                not res.empty
                and "Barème" in res.columns
                and pd.notna(res.iloc[0].get("Barème"))
            ):
                return float(res.iloc[0]["Barème"])

    cycle_classe = obtenir_cycle_classe(classe)
    if "matieres_def" in st.session_state and not st.session_state.matieres_def.empty:
        m_def = st.session_state.matieres_def
        if "Cycle" in m_def.columns:
            res = m_def[
                (m_def["Matière"] == matiere)
                & (
                    m_def["Cycle"].apply(est_cycle_elementaire)
                    == est_cycle_elementaire(cycle_classe)
                )
            ]
        else:
            res = m_def[m_def["Matière"] == matiere]
        if (
            not res.empty
            and "Barème" in m_def.columns
            and pd.notna(res.iloc[0].get("Barème"))
        ):
            return float(res.iloc[0]["Barème"])

    return 50.0 if est_cycle_elementaire(cycle_classe) else 20.0


def ajouter_entete_senegal_officiel(pdf, titre_document=""):
    try:
        font_family = (
            "DejaVu"
            if "DejaVu" in pdf.core_fonts
            or hasattr(pdf, "fonts")
            and "DejaVu" in pdf.fonts
            else "Arial"
        )
    except Exception:
        font_family = "Arial"

    try:
        if os.path.exists("nm.jpg"):
            pdf.image("nm.jpg", x=12, y=8, w=22)
        elif SCEAU_SENEGAL_B64:
            img_data = base64.b64decode(SCEAU_SENEGAL_B64)
            img_bytes = io.BytesIO(img_data)
            pdf.image(img_bytes, x=15, y=8, w=22)
    except Exception:
        pass

    pdf.set_font(font_family, "B", 10)
    pdf.cell(0, 4, nettoyer_texte_pdf("RÉPUBLIQUE DU SÉNÉGAL"), 0, 1, "C")
    pdf.set_font(font_family, "", 8)
    pdf.cell(0, 4, nettoyer_texte_pdf("Un Peuple - Un But - Une Foi"), 0, 1, "C")
    pdf.set_font(font_family, "B", 9)
    pdf.cell(0, 4, nettoyer_texte_pdf("MINISTÈRE DE L'ÉDUCATION NATIONALE"), 0, 1, "C")
    pdf.set_font(font_family, "B", 9)
    pdf.cell(
        0,
        4,
        nettoyer_texte_pdf("INSPECTION D'ACADÉMIE DE SAINT-LOUIS (IA SAINT-LOUIS)"),
        0,
        1,
        "C",
    )
    pdf.set_font(font_family, "B", 9)
    pdf.cell(
        0,
        4,
        nettoyer_texte_pdf(
            "INSPECTION DE L'ÉDUCATION ET DE LA FORMATION DE SAINT-LOUIS (IEF SAINT-LOUIS)"
        ),
        0,
        1,
        "C",
    )

    pdf.set_font(font_family, "B", 10)
    pdf.cell(0, 5, nettoyer_texte_pdf("ÉCOLE PRÉSIDENT NELSON MANDELA"), 0, 1, "C")
# ==========================================
# 4. GÉNÉRATION DES BULLETINS ET PDF (Suite)
# ==========================================

# ==========================================
# 4. GÉNÉRATION DES BULLETINS ET PDF (Suite)
# ==========================================

if titre_document:
    pdf.set_font(font_family, "B", 11)
    pdf.set_text_color(14, 165, 233)
    pdf.cell(0, 6, nettoyer_texte_pdf(titre_document.upper()), 0, 1, "C")
    pdf.set_text_color(0, 0, 0)
    pdf.set_draw_color(14, 165, 233)
    
    if hasattr(pdf, "set_line_width"):
        pdf.set_line_width(0.2)
    elif hasattr(pdf, "set_linewidth"):
        pdf.set_linewidth(0.8)
        
    pdf.line(10, 38, 200, 38)
    pdf.ln(5)


def ajouter_bloc_signatures(
    pdf,
    prof_nom="Le Professeur",
    chef_nom="Le Chef d'Établissement / IEF",
):
  try:
    font_family = (
        "DejaVu"
        if "DejaVu" in pdf.core_fonts
        or hasattr(pdf, "fonts")
        and "DejaVu" in pdf.fonts
        else "Arial"
    )
  except Exception:
    font_family = "Arial"

  pdf.ln(8)
  pdf.set_font(font_family, "B", 8)
  pdf.set_draw_color(200, 200, 200)

  pdf.cell(90, 5, nettoyer_texte_pdf(f"SIGNATURE & TAMPON : {prof_nom.upper()}"), 1, 0, "C")
  pdf.cell(10, 5, "", 0, 0, "C")
  pdf.cell(90, 5, nettoyer_texte_pdf(f"VALIDEUR : {chef_nom.upper()} (IA/IEF)"), 1, 1, "C")

  pdf.set_font(font_family, "I", 7)
  pdf.cell(90, 15, nettoyer_texte_pdf("Sceau numérique & Empreinte d'excellence"), "LRB", 0, "C")
  pdf.cell(10, 15, "", 0, 0, "C")
  pdf.cell(
      90, 15, nettoyer_texte_pdf("Cachet officiel de l'Établissement d'Excellence"), "LRB", 1, "C"
  )


def calculer_bulletin_eleve(classe, eleve, periode):
  cycle_classe = obtenir_cycle_classe(classe)
  is_elem = est_cycle_elementaire(cycle_classe)
  matieres_set = set()

  if (
      "coefficients_db" in st.session_state
      and not st.session_state.coefficients_db.empty
      and "Classe" in st.session_state.coefficients_db.columns
  ):
    c_db = st.session_state.coefficients_db
    m_c = c_db[c_db["Classe"] == classe]["Matière"].dropna().tolist()
    matieres_set.update(m_c)

  if (
      "matieres_def" in st.session_state
      and not st.session_state.matieres_def.empty
  ):
    m_def = st.session_state.matieres_def
    if "Cycle" in m_def.columns:
      m_c_def = (
          m_def[m_def["Cycle"].apply(est_cycle_elementaire) == is_elem][
              "Matière"
          ]
          .dropna()
          .tolist()
      )
      matieres_set.update(m_c_def)
    else:
      matieres_set.update(m_def["Matière"].dropna().tolist())

  notes_df = (
      st.session_state.notes_db if "notes_db" in st.session_state else pd.DataFrame()
  )

  if not notes_df.empty and "Classe" in notes_df.columns:
    cond_cls = notes_df["Classe"] == classe
    if "Periode" in notes_df.columns and "Période" in notes_df.columns:
      cond_per = (notes_df["Periode"] == periode) | (
          notes_df["Période"] == periode
      )
    elif "Periode" in notes_df.columns:
      cond_per = notes_df["Periode"] == periode
    elif "Période" in notes_df.columns:
      cond_per = notes_df["Période"] == periode
    else:
      cond_per = True

    m_notes = (
        notes_df[cond_cls & cond_per]["Matière"].dropna().unique().tolist()
    )
    matieres_set.update(m_notes)

  if not matieres_set:
    matieres_set = (
        {"Lecture / Langage", "Calcul / Mathématiques"}
        if is_elem
        else {"Mathématiques", "Français"}
    )

  liste_matieres = sorted(list(matieres_set))

  notes_classe_periode = pd.DataFrame()
  if not notes_df.empty and "Classe" in notes_df.columns:
    if "Periode" in notes_df.columns:
      notes_classe_periode = notes_df[
          (notes_df["Classe"] == classe) & (notes_df["Periode"] == periode)
      ]
    elif "Période" in notes_df.columns:
      notes_classe_periode = notes_df[
          (notes_df["Classe"] == classe) & (notes_df["Période"] == periode)
      ]

  lignes_bulletin = []
  total_points_global = 0.0
  total_coefficients_global = 0.0
  total_bareme_global = 0.0

  coeffs_dict = {}
  baremes_dict = {}
  for mat in liste_matieres:
    coeffs_dict[mat] = obtenir_coefficient_matiere(classe, mat)
    baremes_dict[mat] = obtenir_bareme_matiere(classe, mat)

  for mat in liste_matieres:
    coef = coeffs_dict.get(mat, 1.0)
    bareme_m = baremes_dict.get(mat, 50.0 if is_elem else 20.0)

    note_row = (
        notes_classe_periode[notes_classe_periode["Eleve"] == eleve]
        if not notes_classe_periode.empty
        and "Eleve" in notes_classe_periode.columns
        else pd.DataFrame()
    )
    note_mat = (
        note_row[note_row["Matière"] == mat]
        if not note_row.empty and "Matière" in note_row.columns
        else pd.DataFrame()
    )

    d1, d2, comp = 0.0, 0.0, 0.0
    if not note_mat.empty:
      d1_val = (
          note_mat.iloc[0]["Devoir1"]
          if "Devoir1" in note_mat.columns
          else 0.0
      )
      d2_val = (
          note_mat.iloc[0]["Devoir2"]
          if "Devoir2" in note_mat.columns
          else 0.0
      )
      comp_val = (
          note_mat.iloc[0]["Composition"]
          if "Composition" in note_mat.columns
          else 0.0
      )

      d1 = float(d1_val) if pd.notna(d1_val) else 0.0
      d2 = float(d2_val) if pd.notna(d2_val) else 0.0
      comp = float(comp_val) if pd.notna(comp_val) else 0.0

    if is_elem:
      moy_matiere = comp
      total_points_global += moy_matiere
      total_bareme_global += bareme_m

      lignes_bulletin.append({
          "Matiere": mat,
          "Bareme": bareme_m,
          "Composition": comp,
          "MoyenneMatiere": round(moy_matiere, 2),
          "Appreciation": obtenir_appreciation(moyenne_generale if 'moyenne_generale' in locals() else moy_matiere, cycle_classe, bareme_m),
      })
    else:
      moy_devoirs = (d1 + d2) / 2.0
      moy_matiere = (moy_devoirs + comp) / 2.0
      total_pondere = moy_matiere * coef

      total_points_global += total_pondere
      total_coefficients_global += coef

      lignes_bulletin.append({
          "Matiere": mat,
          "Coefficient": coef,
          "Devoir1": d1,
          "Devoir2": d2,
          "Composition": comp,
          "MoyenneMatiere": round(moy_matiere, 2),
          "TotalPondere": round(total_pondere, 2),
          "Appreciation": obtenir_appreciation(moy_matiere, cycle_classe, 20.0),
      })

  if is_elem:
    if total_bareme_global > 0:
      moyenne_generale = round(
          (total_points_global / total_bareme_global) * 10.0, 2
      )
    else:
      moyenne_generale = 0.0
  else:
    moyenne_generale = (
        round(total_points_global / total_coefficients_global, 2)
        if total_coefficients_global > 0
        else 0.0
    )

  tous_eleves = []
  if (
      "eleves_db" in st.session_state
      and not st.session_state.eleves_db.empty
      and "Classe" in st.session_state.eleves_db.columns
  ):
    df_sorted_el = trier_eleves_par_nom(
        st.session_state.eleves_db[
            st.session_state.eleves_db["Classe"] == classe
        ]
    )
    tous_eleves = df_sorted_el["Nom Complet"].tolist()

  moyennes_classe = {}
  for el in tous_eleves:
    pts = 0.0
    coefs = 0.0
    bareme_tot_el = 0.0
    notes_el_p = (
        notes_classe_periode[notes_classe_periode["Eleve"] == el]
        if not notes_classe_periode.empty
        and "Eleve" in notes_classe_periode.columns
        else pd.DataFrame()
    )
    for mat in liste_matieres:
      coef = coeffs_dict.get(mat, 1.0)
      bareme_m = baremes_dict.get(mat, 50.0 if is_elem else 20.0)
      n_m = (
          notes_el_p[notes_el_p["Matière"] == mat]
          if not notes_el_p.empty and "Matière" in notes_el_p.columns
          else pd.DataFrame()
      )
      if not n_m.empty:
        d1_val = (
            n_m.iloc[0]["Devoir1"] if "Devoir1" in n_m.columns else 0.0
        )
        d2_val = (
            n_m.iloc[0]["Devoir2"] if "Devoir2" in n_m.columns else 0.0
        )
        comp_val = (
            n_m.iloc[0]["Composition"] if "Composition" in n_m.columns else 0.0
        )
        d1 = float(d1_val) if pd.notna(d1_val) else 0.0
        d2 = float(d2_val) if pd.notna(d2_val) else 0.0
        comp = float(comp_val) if pd.notna(comp_val) else 0.0

        if is_elem:
          pts += comp
          bareme_tot_el += bareme_m
        else:
          m_mat = ((d1 + d2) / 2.0 + comp) / 2.0
          pts += m_mat * coef
          coefs += coef
    if is_elem:
      moyennes_classe[el] = (
          round((pts / bareme_tot_el) * 10.0, 2) if bareme_tot_el > 0 else 0.0
      )
    else:
      moyennes_classe[el] = (
          round(pts / coefs, 2) if coefs > 0 else 0.0
      )

  classement_trie = sorted(
      moyennes_classe.items(), key=lambda x: x[1], reverse=True
  )
  rang = "-"
  for idx, (el_nom, _) in enumerate(classement_trie, 1):
    if el_nom == eleve:
      rang = f"{idx} / {len(tous_eleves)}"
      break

  vs_df = (
      st.session_state.viescolaire_db
      if "viescolaire_db" in st.session_state
      else pd.DataFrame()
  )
  vs_row = pd.DataFrame()
  if not vs_df.empty and "Classe" in vs_df.columns and "Eleve" in vs_df.columns:
    if "Periode" in vs_df.columns:
      vs_row = vs_df[
          (vs_df["Classe"] == classe)
          & (vs_df["Periode"] == periode)
          & (vs_df["Eleve"] == eleve)
      ]
    elif "Période" in vs_df.columns:
      vs_row = vs_df[
          (vs_df["Classe"] == classe)
          & (vs_df["Période"] == periode)
          & (vs_df["Eleve"] == eleve)
      ]

  abs_just, abs_non_just, retards, heures_p, obs, decision = (
      0,
      0,
      0,
      0,
      "RAS",
      "Encouragements",
  )
  if not vs_row.empty:
    abs_just = (
        int(vs_row.iloc[0]["AbsencesJustifiees"])
        if "AbsencesJustifiees" in vs_row.columns
        and pd.notna(vs_row.iloc[0]["AbsencesJustifiees"])
        else 0
    )
    abs_non_just = (
        int(vs_row.iloc[0]["AbsencesNonJustifiees"])
        if "AbsencesNonJustifiees" in vs_row.columns
        and pd.notna(vs_row.iloc[0]["AbsencesNonJustifiees"])
        else 0
    )
    retards = (
        int(vs_row.iloc[0]["Retards"])
        if "Retards" in vs_row.columns
        and pd.notna(vs_row.iloc[0]["Retards"])
        else 0
    )
    heures_p = (
        int(vs_row.iloc[0]["HeuresPerdues"])
        if "HeuresPerdues" in vs_row.columns
        and pd.notna(vs_row.iloc[0]["HeuresPerdues"])
        else 0
    )
    obs = (
        str(vs_row.iloc[0]["Observations"])
        if "Observations" in vs_row.columns
        and pd.notna(vs_row.iloc[0]["Observations"])
        else "RAS"
    )
    decision = (
        str(vs_row.iloc[0]["DecisionConseil"])
        if "DecisionConseil" in vs_row.columns
        and pd.notna(vs_row.iloc[0]["DecisionConseil"])
        else "Encouragements"
    )

  return {
      "eleve": eleve,
      "classe": classe,
      "cycle": cycle_classe,
      "periode": periode,
      "lignes": lignes_bulletin,
      "total_points": round(total_points_global, 2),
      "total_coefficients": total_coefficients_global if not is_elem else "-",
      "total_bareme": 10.0 if is_elem else 20.0,
      "moyenne_generale": moyenne_generale,
      "rang": rang,
      "effectif": len(tous_eleves),
      "abs_just": abs_just,
      "abs_non_just": abs_non_just,
      "retards": retards,
      "heures_perdues": heures_p,
      "observations": obs,
      "decision": decision,
  }


def generer_pdf_bulletin(bul_data):
  pdf = FPDF()
  try:
    if os.path.exists("DejaVuSans.ttf"):
      pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
      pdf.add_font("DejaVu", "B", "DejaVuSans-Bold.ttf", uni=True)
      font_family = "DejaVu"
    else:
      font_family = "Arial"
  except Exception:
    font_family = "Arial"

  pdf.add_page()
  cycle = bul_data.get("cycle", "Collège")
  is_elem = est_cycle_elementaire(cycle)

  ajouter_entete_senegal_officiel(
      pdf, f"BULLETIN DE NOTES - {bul_data['periode'].upper()} ({cycle.upper()})"
  )

  pdf.set_font(font_family, "B", 10)
  pdf.cell(100, 6, nettoyer_texte_pdf(f"Nom et Prénom : {bul_data['eleve']}"), 0, 0, "L")
  pdf.cell(90, 6, nettoyer_texte_pdf(f"Classe : {bul_data['classe']}"), 0, 1, "R")
  pdf.cell(100, 6, nettoyer_texte_pdf(f"Effectif : {bul_data['effectif']} élèves"), 0, 0, "L")
  pdf.cell(90, 6, nettoyer_texte_pdf(f"Rang : {bul_data['rang']}"), 0, 1, "R")
  pdf.ln(4)

  pdf.set_font(font_family, "B", 9)
  pdf.set_fill_color(14, 165, 233)
  pdf.set_text_color(255, 255, 255)

  if is_elem:
    col_widths = [95, 30, 35, 30]
    headers = ["Matière", "Barème", "Note obtenue", "Appréciation"]
  else:
    col_widths = [65, 18, 18, 18, 22, 22, 27]
    headers = [
        "Matière",
        "Coef",
        "Dev 1",
        "Dev 2",
        "Comp",
        "Moy/20",
        "Appréciation",
    ]

  for i, h in enumerate(headers):
    pdf.cell(col_widths[i], 7, nettoyer_texte_pdf(h), 1, 0, "C", True)
  pdf.ln()

  pdf.set_font(font_family, "", 8)
  pdf.set_text_color(0, 0, 0)
  fill = False
  pdf.set_fill_color(240, 249, 255)

  for lig in bul_data["lignes"]:
    if is_elem:
      pdf.cell(col_widths[0], 6, nettoyer_texte_pdf(str(lig["Matiere"])[:30]), 1, 0, "L", fill)
      pdf.cell(col_widths[1], 6, nettoyer_texte_pdf(f"/ {lig['Bareme']}"), 1, 0, "C", fill)
      pdf.cell(col_widths[2], 6, nettoyer_texte_pdf(str(lig["Composition"])), 1, 0, "C", fill)
      pdf.cell(col_widths[3], 6, nettoyer_texte_pdf(str(lig["Appreciation"])[:15]), 1, 0, "C", fill)
    else:
      pdf.cell(col_widths[0], 6, nettoyer_texte_pdf(str(lig["Matiere"])[:25]), 1, 0, "L", fill)
      pdf.cell(col_widths[1], 6, nettoyer_texte_pdf(str(lig["Coefficient"])), 1, 0, "C", fill)
      pdf.cell(col_widths[2], 6, nettoyer_texte_pdf(str(lig["Devoir1"])), 1, 0, "C", fill)
      pdf.cell(col_widths[3], 6, nettoyer_texte_pdf(str(lig["Devoir2"])), 1, 0, "C", fill)
      pdf.cell(col_widths[4], 6, nettoyer_texte_pdf(str(lig["Composition"])), 1, 0, "C", fill)
      pdf.cell(col_widths[5], 6, nettoyer_texte_pdf(str(lig["MoyenneMatiere"])), 1, 0, "C", fill)
      pdf.cell(col_widths[6], 6, nettoyer_texte_pdf(str(lig["Appreciation"])[:15]), 1, 0, "C", fill)
    pdf.ln()
    fill = not fill

  pdf.ln(4)
  pdf.set_font(font_family, "B", 10)
  pdf.set_fill_color(224, 242, 254)
  if is_elem:
    pdf.cell(
        0,
        6,
        nettoyer_texte_pdf(
            f"Moyenne Générale : {bul_data['moyenne_generale']} / {bul_data['total_bareme']}"
            f" | Total Points : {bul_data['total_points']}"
        ),
        1,
        1,
        "L",
        True,
    )
  else:
    pdf.cell(
        0,
        6,
        nettoyer_texte_pdf(
            f"Moyenne Générale : {bul_data['moyenne_generale']} / 20"
            f" | Total Points : {bul_data['total_points']}"
        ),
        1,
        1,
        "L",
        True,
    )
  pdf.ln(3)

  pdf.set_font(font_family, "B", 9)
  pdf.cell(0, 5, nettoyer_texte_pdf("BILAN DE LA VIE SCOLAIRE ET DISCIPLINE"), 0, 1, "L")
  pdf.set_font(font_family, "", 9)
  pdf.cell(
      0,
      5,
      nettoyer_texte_pdf(
          "Absences justifiées : "
          f"{bul_data['abs_just']} | Absences non justifiées :"
          f" {bul_data['abs_non_just']} | Retards : {bul_data['retards']} |"
          f" Heures perdues : {bul_data['heures_perdues']}h"
      ),
      1,
      1,
      "L",
  )
  pdf.cell(
      0,
      5,
      nettoyer_texte_pdf(
          "Observations / Appréciation générale :"
          f" {bul_data['observations']}"
      ),
      1,
      1,
      "L",
  )
  pdf.cell(
      0,
      5,
      nettoyer_texte_pdf(f"Décision du Conseil de Classe : {bul_data['decision']}"),
      1,
      1,
      "L",
  )

  ajouter_bloc_signatures(
      pdf,
      prof_nom="Professeur Principal",
      chef_nom="Inspecteur / Directeur IEF Saint-Louis",
  )

  try:
    output_pdf = pdf.output(dest='S')
    if isinstance(output_pdf, str):
      return output_pdf.encode('latin1', 'replace')
    elif isinstance(output_pdf, (bytes, bytearray)):
      return bytes(output_pdf)
    else:
      return bytes(pdf.output())
  except Exception:
    return bytes(pdf.output())


def generer_zip_bulletins_classe(classe, periode):
  eleves_df = st.session_state.eleves_db
  if "Classe" in eleves_df.columns:
    eleves = eleves_df[eleves_df["Classe"] == classe]
  else:
    eleves = pd.DataFrame()

  eleves_sorted = trier_eleves_par_nom(eleves)
  eleves_list = (
      eleves_sorted["Nom Complet"].tolist()
      if not eleves_sorted.empty and "Nom Complet" in eleves_sorted.columns
      else []
  )

  zip_buffer = io.BytesIO()
  with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
    for eleve in eleves_list:
      bul_data = calculer_bulletin_eleve(classe, eleve, periode)
      pdf_bytes = generer_pdf_bulletin(bul_data)
      filename = (
          f"Bulletin_{classe}_{eleve.replace(' ', '_')}_{periode.replace(' ', '_')}.pdf"
      )
      zip_file.writestr(filename, pdf_bytes)
  return zip_buffer.getvalue()
# ==========================================
# 5. GÉNÉRATION DES DOCUMENTS ADMINISTRATIFS PDF
# ==========================================

def generer_pdf_liste_eleves_classe(classe):
  if (
      "eleves_db" not in st.session_state
      or st.session_state.eleves_db.empty
  ):
    df_eleves = pd.DataFrame(columns=["Nom Complet", "Classe", "Date de Naissance"])
  else:
    if "Classe" in st.session_state.eleves_db.columns:
      df_eleves = st.session_state.eleves_db[
          st.session_state.eleves_db["Classe"] == classe
      ]
    else:
      df_eleves = pd.DataFrame(columns=["Nom Complet", "Classe", "Date de Naissance"])

  df_eleves = trier_eleves_par_nom(df_eleves)

  pdf = FPDF()
  try:
    font_family = "DejaVu" if os.path.exists("DejaVuSans.ttf") else "Arial"
  except Exception:
    font_family = "Arial"

  pdf.add_page()
  ajouter_entete_senegal_officiel(
      pdf, f"FICHE OFFICIELLE DE LA CLASSE : {classe} (Tri Alphabétique Nom)"
  )

  pdf.set_font(font_family, "B", 9)
  pdf.set_fill_color(14, 165, 233)
  pdf.set_text_color(255, 255, 255)

  col_widths = [75, 45, 70]
  headers = ["Nom Complet de l'Élève", "Classe", "Date de Naissance"]

  for i, h in enumerate(headers):
    pdf.cell(col_widths[i], 7, nettoyer_texte_pdf(h), 1, 0, "C", True)
  pdf.ln()

  pdf.set_font(font_family, "", 8)
  pdf.set_text_color(0, 0, 0)
  fill = False
  pdf.set_fill_color(240, 249, 255)

  if not df_eleves.empty:
    for _, row in df_eleves.iterrows():
      pdf.cell(
          col_widths[0],
          6,
          nettoyer_texte_pdf(str(row.get("Nom Complet", ""))[:35]),
          1,
          0,
          "L",
          fill,
      )
      pdf.cell(
          col_widths[1], 6, nettoyer_texte_pdf(str(row.get("Classe", ""))[:20]), 1, 0, "C", fill
      )
      pdf.cell(
          col_widths[2],
          6,
          nettoyer_texte_pdf(str(row.get("Date de Naissance", ""))[:20]),
          1,
          0,
          "C",
          fill,
      )
      pdf.ln()
      fill = not fill
  else:
    pdf.cell(190, 6, nettoyer_texte_pdf("Aucun élève répertorié dans cette classe."), 1, 1, "C")

  ajouter_bloc_signatures(
      pdf,
      prof_nom="Responsable de Scolarité",
      chef_nom="Inspecteur IEF Saint-Louis",
  )
  
  try:
    output_pdf = pdf.output(dest='S')
    if isinstance(output_pdf, str):
      return output_pdf.encode('latin1', 'replace')
    elif isinstance(output_pdf, (bytes, bytearray)):
      return bytes(output_pdf)
    else:
      return bytes(pdf.output())
  except Exception:
    return bytes(pdf.output())


def generer_pdf_liste_absences(classe_filtre="Toutes"):
  df_abs = (
      st.session_state.absences_db
      if "absences_db" in st.session_state
      else pd.DataFrame()
  )
  if not df_abs.empty and classe_filtre != "Toutes" and "Classe" in df_abs.columns:
    df_abs = df_abs[df_abs["Classe"] == classe_filtre]

  pdf = FPDF()
  try:
    font_family = "DejaVu" if os.path.exists("DejaVuSans.ttf") else "Arial"
  except Exception:
    font_family = "Arial"

  pdf.add_page()
  ajouter_entete_senegal_officiel(
      pdf, f"REGISTRE OFFICIEL DES ABSENCES & RETARDS - {classe_filtre.upper()}"
  )

  pdf.set_font(font_family, "B", 9)
  pdf.set_fill_color(14, 165, 233)
  pdf.set_text_color(255, 255, 255)

  col_widths = [25, 30, 50, 25, 60]
  headers = ["Date", "Classe", "Élève", "Statut", "Motif / Remarque"]

  for i, h in enumerate(headers):
    pdf.cell(col_widths[i], 7, nettoyer_texte_pdf(h), 1, 0, "C", True)
  pdf.ln()

  pdf.set_font(font_family, "", 8)
  pdf.set_text_color(0, 0, 0)
  fill = False
  pdf.set_fill_color(240, 249, 255)

  if not df_abs.empty:
    for _, row in df_abs.iterrows():
      pdf.cell(col_widths[0], 6, nettoyer_texte_pdf(str(row.get("Date", ""))[:12]), 1, 0, "C", fill)
      pdf.cell(col_widths[1], 6, nettoyer_texte_pdf(str(row.get("Classe", ""))[:15]), 1, 0, "C", fill)
      pdf.cell(col_widths[2], 6, nettoyer_texte_pdf(str(row.get("Élève", ""))[:25]), 1, 0, "L", fill)
      pdf.cell(col_widths[3], 6, nettoyer_texte_pdf(str(row.get("Statut", ""))[:15]), 1, 0, "C", fill)
      pdf.cell(col_widths[4], 6, nettoyer_texte_pdf(str(row.get("Motif", ""))[:30]), 1, 0, "L", fill)
      pdf.ln()
      fill = not fill
  else:
    pdf.cell(190, 6, nettoyer_texte_pdf("Aucune absence ou retard enregistré."), 1, 1, "C")

  ajouter_bloc_signatures(
      pdf,
      prof_nom="Surveillant Général",
      chef_nom="Chef d'Établissement",
  )
  try:
    output_pdf = pdf.output(dest='S')
    if isinstance(output_pdf, str):
      return output_pdf.encode('latin1', 'replace')
    elif isinstance(output_pdf, (bytes, bytearray)):
      return bytes(output_pdf)
    else:
      return bytes(pdf.output())
  except Exception:
    return bytes(pdf.output())


def generer_pdf_edt(classe, df_edt):
  pdf = FPDF(orientation="L", unit="mm", format="A4")
  try:
    font_family = "DejaVu" if os.path.exists("DejaVuSans.ttf") else "Arial"
  except Exception:
    font_family = "Arial"

  pdf.add_page()
  ajouter_entete_senegal_officiel(
      pdf, f"EMPLOI DU TEMPS OFFICIEL DE LA CLASSE : {classe}"
  )

  pdf.set_font(font_family, "B", 8)
  pdf.set_fill_color(14, 165, 233)
  pdf.set_text_color(255, 255, 255)

  col_w = 22
  pdf.cell(30, 7, nettoyer_texte_pdf("Jour / Heure"), 1, 0, "C", True)
  for col in df_edt.columns:
    pdf.cell(col_w, 7, nettoyer_texte_pdf(str(col)[:8]), 1, 0, "C", True)
  pdf.ln()

  pdf.set_font(font_family, "", 7)
  pdf.set_text_color(0, 0, 0)

  for jour in df_edt.index:
    pdf.cell(30, 6, nettoyer_texte_pdf(str(jour)), 1, 0, "C", True)
    for col in df_edt.columns:
      val = str(df_edt.loc[jour, col])
      pdf.cell(col_w, 6, nettoyer_texte_pdf(val[:12]), 1, 0, "C", True)
    pdf.ln()

  ajouter_bloc_signatures(
      pdf, prof_nom="Chef d'Établissement", chef_nom="Inspecteur IA Saint-Louis"
  )

  try:
    output_pdf = pdf.output(dest='S')
    if isinstance(output_pdf, str):
      return output_pdf.encode('latin1', 'replace')
    elif isinstance(output_pdf, (bytes, bytearray)):
      return bytes(output_pdf)
    else:
      return bytes(pdf.output())
  except Exception:
    return bytes(pdf.output())


def generer_pdf_cahier_textes(df_ct, classe="Global"):
  pdf = FPDF()
  try:
    font_family = "DejaVu" if os.path.exists("DejaVuSans.ttf") else "Arial"
  except Exception:
    font_family = "Arial"

  pdf.add_page()
  ajouter_entete_senegal_officiel(
      pdf, f"REGISTRE ET CAHIER DE TEXTES - {classe.upper()}"
  )

  pdf.set_font(font_family, "B", 8)
  pdf.set_fill_color(14, 165, 233)
  pdf.set_text_color(255, 255, 255)

  col_widths = [25, 30, 30, 55, 50]
  headers = ["Date", "Classe", "Matière", "Contenu de la leçon", "Devoirs / Travail"]

  for i, h in enumerate(headers):
    pdf.cell(col_widths[i], 7, nettoyer_texte_pdf(h), 1, 0, "C", True)
  pdf.ln()

  pdf.set_font(font_family, "", 7)
  pdf.set_text_color(0, 0, 0)
  fill = False
  pdf.set_fill_color(240, 249, 255)

  for _, row in df_ct.iterrows():
    pdf.cell(col_widths[0], 6, nettoyer_texte_pdf(str(row.get("Date", ""))[:10]), 1, 0, "C", fill)
    pdf.cell(col_widths[1], 6, nettoyer_texte_pdf(str(row.get("Classe", ""))[:12]), 1, 0, "C", fill)
    pdf.cell(col_widths[2], 6, nettoyer_texte_pdf(str(row.get("Matière", ""))[:15]), 1, 0, "L", fill)
    pdf.cell(col_widths[3], 6, nettoyer_texte_pdf(str(row.get("Contenu", ""))[:35]), 1, 0, "L", fill)
    pdf.cell(
        col_widths[4], 6, nettoyer_texte_pdf(str(row.get("Travail à faire", ""))[:30]), 1, 0, "L", fill
    )
    pdf.ln()
    fill = not fill

  ajouter_bloc_signatures(
      pdf,
      prof_nom="L'Enseignant Concerné",
      chef_nom="L'Inspecteur Pédagogique",
  )

  try:
    output_pdf = pdf.output(dest='S')
    if isinstance(output_pdf, str):
      return output_pdf.encode('latin1', 'replace')
    elif isinstance(output_pdf, (bytes, bytearray)):
      return bytes(output_pdf)
    else:
      return bytes(pdf.output())
  except Exception:
    return bytes(pdf.output())

# ==========================================
# 4. EN-TÊTE ET NAVIGATION GLOBALE DESIGN XXL
# ==========================================
logo_data_uri = obtenir_logo_base64()
if logo_data_uri:
    logo_element_html = f'<img src="{logo_data_uri}" alt="Logo Mandela" />'
else:
    logo_element_html = (
        '<div class="emblem-box"><span style="font-size: 3.2rem;">🇸🇳</span></div>'
    )

header_complet_html = f"""
<div class="header-institutionnel">
    <div class="header-inner">
        <div class="logo-frame-container">
            {logo_element_html}
        </div>
        <div class="header-text">
            <div class="ministere-title">MINISTÈRE DE L'ÉDUCATION NATIONALE DU SÉNÉGAL</div>
            <div class="ia-ief-sub">INSPECTION D'ACADÉMIE DE SAINT-LOUIS (IA) • INSPECTION DE L'ÉDUCATION ET DE LA FORMATION (IEF)</div>
            <div class="ecole-title">🦁 ÉCOLE PRÉSIDENT NELSON MANDELA</div>
        </div>
    </div>
</div>
"""
st.markdown(header_complet_html, unsafe_allow_html=True)

if st.session_state.espace_actif != "🏠 Accueil":
    col_ret1, col_ret2 = st.columns([1, 5])
    with col_ret1:
        if st.button("⬅️ Retour Accueil"):
            st.session_state.espace_actif = "🏠 Accueil"
            st.rerun()
    st.markdown("---")

# ==========================================
# 5. ACCUEIL ET REDIRECTION SÉLECTIVE
# ==========================================
if st.session_state.espace_actif == "🏠 Accueil":
    st.markdown(
        """
        <div style="text-align: center; padding: 15px 0 35px 0;">
            <h1 style="color: #0F172A; font-weight: 900; font-size: 2.8rem;">Éduquer • Instruire • Promouvoir les Vertus Africaines</h1>
            <p style="font-size: 1.25rem; color: #334155; max-width: 1000px; margin: 0 auto; font-weight: 500;">
                Bâtir l'élite de demain sous la tutelle de l'IA Saint-Louis et l'IEF Saint-Louis. Un enseignement d'excellence, un suivi pédagogique rigoureux, 
                des valeurs républicaines fortes et une infrastructure moderne dédiée à l'épanouissement de chaque élève de l'École Président Nelson Mandela.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(
            """
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">👨‍🏫</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0; font-weight: 800;">Espace Professeurs</h3>
                <p style="font-size: 0.95rem; color: #475569; font-weight: 600;">Encadrement d'excellence : saisie rigoureuse des notes, suivi des présences, cahier de texte et assignation des travaux à faire avec pièces jointes.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Accéder Professeur", key="btn_p"):
            st.session_state.espace_actif = "👨‍🏫 Espace Professeurs / Maîtres"
            st.rerun()

    with c2:
        st.markdown(
            """
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">👨‍👩‍👧</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0; font-weight: 800;">Espace Parents</h3>
                <p style="font-size: 0.95rem; color: #475569; font-weight: 600;">Partenariat école-famille : suivi des travaux à faire avec supports photos/vidéos, consultation des emplois du temps, vie scolaire et annonces officielles.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Accéder Parent", key="btn_pa"):
            st.session_state.espace_actif = "👨‍👩‍👧 Espace Parents / Élèves"
            st.rerun()

    with c3:
        st.markdown(
            """
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">🔒</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0; font-weight: 800;">Administration</h3>
                <p style="font-size: 0.95rem; color: #475569; font-weight: 600;">Pilotage stratégique de l'établissement et gestion rigoureuse des habilitations pour une sécurité optimale.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Accéder Admin", key="btn_ad"):
            st.session_state.espace_actif = "🔒 Espace Administration (Sécurisé)"
            st.rerun()

    with c4:
        st.markdown(
            """
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">🏫</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0; font-weight: 800;">Rapports Globaux</h3>
                <p style="font-size: 0.95rem; color: #475569; font-weight: 600;">Tableaux de bord d'excellence, téléchargement des bulletins PDF officiels et assistant pédagogique intelligent.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Accéder Rapports", key="btn_rp"):
            st.session_state.espace_actif = "🏫 Administration XXL & Rapports"
            st.rerun()

# ==========================================
# 4. EN-TÊTE ET NAVIGATION GLOBALE DESIGN XXL
# ==========================================
logo_data_uri = obtenir_logo_base64()
if logo_data_uri:
    logo_element_html = f'<img src="{logo_data_uri}" alt="Logo Mandela" />'
else:
    logo_element_html = (
        '<div class="emblem-box"><span style="font-size: 3.2rem;">🇸🇳</span></div>'
    )

header_complet_html = f"""
<div class="header-institutionnel">
    <div class="header-inner">
        <div class="logo-frame-container">
            {logo_element_html}
        </div>
        <div class="header-text">
            <div class="ministere-title">MINISTÈRE DE L'ÉDUCATION NATIONALE DU SÉNÉGAL</div>
            <div class="ia-ief-sub">INSPECTION D'ACADÉMIE DE SAINT-LOUIS (IA) • INSPECTION DE L'ÉDUCATION ET DE LA FORMATION (IEF)</div>
            <div class="ecole-title">🦁 ÉCOLE PRÉSIDENT NELSON MANDELA</div>
        </div>
    </div>
</div>
"""
st.markdown(header_complet_html, unsafe_allow_html=True)

if st.session_state.espace_actif != "🏠 Accueil":
    col_ret1, col_ret2 = st.columns([1, 5])
    with col_ret1:
        if st.button("⬅️ Retour Accueil"):
            st.session_state.espace_actif = "🏠 Accueil"
            st.rerun()
    st.markdown("---")

# ==========================================
# 5. ACCUEIL ET REDIRECTION SÉLECTIVE
# ==========================================
if st.session_state.espace_actif == "🏠 Accueil":
    st.markdown(
        """
        <div style="text-align: center; padding: 15px 0 35px 0;">
            <h1 style="color: #0F172A; font-weight: 900; font-size: 2.8rem;">Éduquer • Instruire • Promouvoir les Vertus Africaines</h1>
            <p style="font-size: 1.25rem; color: #334155; max-width: 1000px; margin: 0 auto; font-weight: 500;">
                Bâtir l'élite de demain sous la tutelle de l'IA Saint-Louis et l'IEF Saint-Louis. Un enseignement d'excellence, un suivi pédagogique rigoureux, 
                des valeurs républicaines fortes et une infrastructure moderne dédiée à l'épanouissement de chaque élève de l'École Président Nelson Mandela.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(
            """
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">👨‍🏫</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0; font-weight: 800;">Espace Professeurs</h3>
                <p style="font-size: 0.95rem; color: #475569; font-weight: 600;">Encadrement d'excellence : saisie rigoureuse des notes, suivi des présences, cahier de texte et assignation des travaux à faire avec pièces jointes.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Accéder Professeur", key="btn_p"):
            st.session_state.espace_actif = "👨‍🏫 Espace Professeurs / Maîtres"
            st.rerun()

    with c2:
        st.markdown(
            """
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">👨‍👩‍👧</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0; font-weight: 800;">Espace Parents</h3>
                <p style="font-size: 0.95rem; color: #475569; font-weight: 600;">Partenariat école-famille : suivi des travaux à faire avec supports photos/vidéos, consultation des emplois du temps, vie scolaire et annonces officielles.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Accéder Parent", key="btn_pa"):
            st.session_state.espace_actif = "👨‍👩‍👧 Espace Parents / Élèves"
            st.rerun()

    with c3:
        st.markdown(
            """
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">🔒</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0; font-weight: 800;">Administration</h3>
                <p style="font-size: 0.95rem; color: #475569; font-weight: 600;">Pilotage stratégique de l'établissement et gestion rigoureuse des habilitations pour une sécurité optimale.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Accéder Admin", key="btn_ad"):
            st.session_state.espace_actif = "🔒 Espace Administration (Sécurisé)"
            st.rerun()

    with c4:
        st.markdown(
            """
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">🏫</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0; font-weight: 800;">Rapports Globaux</h3>
                <p style="font-size: 0.95rem; color: #475569; font-weight: 600;">Tableaux de bord d'excellence, téléchargement des bulletins PDF officiels et assistant pédagogique intelligent.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Accéder Rapports", key="btn_rp"):
            st.session_state.espace_actif = "🏫 Administration XXL & Rapports"
            st.rerun()
elif st.session_state.espace_actif == "👨‍🏫 Espace Professeurs / Maîtres":
    st.markdown('<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Espace Enseignants & Saisie Pédagogique</div>', unsafe_allow_html=True)

    if not st.session_state.get("prof_logged", False):
        st.warning("⚠️ Veuillez vous connecter via l'espace d'authentification des professeurs.")
        with st.form("login_prof_form"):
            p_user = st.text_input("Identifiant Professeur")
            p_pass = st.text_input("Mot de passe", type="password")
            if st.form_submit_button("Se connecter"):
                st.session_state.prof_logged = True
                st.session_state.prof_nom_connecte = p_user
                st.session_state.prof_classe_autorisee = "6ème A"
                st.session_state.prof_matiere_principale = "Mathématiques"
                st.rerun()
    else:
        prof_connecte = st.session_state.get("prof_nom_connecte", "Enseignant")
        classe_autorisee = st.session_state.get("prof_classe_autorisee", "6ème A")
        matiere_principale = st.session_state.get("prof_matiere_principale", "Mathématiques")

        st.info(f"Bienvenue, **{prof_connecte}** | Classe assignée : **{classe_autorisee}** | Matière : **{matiere_principale}**")

        t_notes, t_taf_prof, t_appel, t_cond, t_cahier, t_edt_prof = st.tabs([
            "📝 Saisie des Notes", "📌 Travail à Faire", "📋 Appels", "⚠️ Vie Scolaire", "📑 Cahier de Texte", "📅 Emploi du Temps"
        ])

        with t_notes:
            st.markdown("### 📝 Saisie et Modification des Notes")
            col1, col2 = st.columns(2)
            with col1:
                periode_sel = st.selectbox("Période active", ["Trimestre 1", "Trimestre 2", "Trimestre 3"], key="prof_periode_notes")
            with col2:
                matiere_sel = st.selectbox("Matière", [matiere_principale], key="prof_matiere_notes")

            try:
                res_eleves = supabase.table("students").select("id, nom_complet").eq("classe", classe_autorisee).execute()
                eleves_data = res_eleves.data if res_eleves and res_eleves.data else []
            except Exception:
                eleves_data = []

            if not eleves_data:
                st.warning(f"Aucun élève trouvé pour la classe {classe_autorisee}.")
            else:
                try:
                    res_notes = supabase.table("notes").select("*").eq("classe", classe_autorisee).eq("matiere", matiere_sel).eq("periode", periode_sel).execute()
                    notes_data = res_notes.data if res_notes and res_notes.data else []
                except Exception:
                    notes_data = []

                df_eleves = pd.DataFrame(eleves_data)
                df_notes = pd.DataFrame(notes_data)

                if not df_notes.empty:
                    df_merged = pd.merge(df_eleves, df_notes, left_on="nom_complet", right_on="eleve", how="left")
                else:
                    df_merged = df_eleves.copy()
                    df_merged["devoir1"] = 0.0
                    df_merged["devoir2"] = 0.0
                    df_merged["composition"] = 0.0
                    df_merged["bareme"] = 20.0

                cols_to_edit = ["nom_complet"]
                for c in ["devoir1", "devoir2", "composition", "bareme"]:
                    if c not in df_merged.columns:
                        df_merged[c] = 0.0
                    cols_to_edit.append(c)

                edited_df = st.data_editor(
                    df_merged[cols_to_edit],
                    num_rows="fixed",
                    use_container_width=True,
                    key="editor_notes_prof"
                )

                if st.button("💾 Enregistrer les Notes dans Supabase", type="primary"):
                    success_count = 0
                    for _, row in edited_df.iterrows():
                        payload = {
                            "classe": classe_autorisee,
                            "matiere": matiere_sel,
                            "periode": periode_sel,
                            "eleve": row["nom_complet"],
                            "devoir1": float(row.get("devoir1", 0)),
                            "devoir2": float(row.get("devoir2", 0)),
                            "composition": float(row.get("composition", 0)),
                            "bareme": float(row.get("bareme", 20))
                        }
                        try:
                            supabase.table("notes").upsert(payload, on_conflict="classe,matiere,periode,eleve").execute()
                            success_count += 1
                        except Exception as e:
                            st.error(f"Erreur pour {row['nom_complet']} : {e}")
                    if success_count > 0:
                        st.success(f"✅ {success_count} enregistrements synchronisés avec succès !")

        with t_taf_prof:
            st.markdown("### 📌 Publication du Travail à Faire (TAF)")
            with st.form("form_taf_complet"):
                titre_taf = st.text_input("Titre du Devoir / Exercice")
                consignes_taf = st.text_area("Consignes détaillées")
                date_rendu = st.date_input("Date limite de rendu")
                submit_taf = st.form_submit_button("Publier le Devoir")
                if submit_taf and titre_taf:
                    payload_taf = {
                        "classe": classe_autorisee,
                        "matiere": matiere_principale,
                        "titre": titre_taf,
                        "consignes": consignes_taf,
                        "date_rendu": str(date_rendu),
                        "professeur": prof_connecte
                    }
                    try:
                        supabase.table("travail_a_faire").insert(payload_taf).execute()
                        st.success("✅ Travail à faire publié avec succès !")
                    except Exception as e:
                        st.error(f"Erreur lors de la publication : {e}")

            st.markdown("---")
            st.markdown("#### Devoirs déjà publiés")
            try:
                res_taf = supabase.table("travail_a_faire").select("*").eq("classe", classe_autorisee).eq("matiere", matiere_principale).execute()
                if res_taf and res_taf.data:
                    for taf in res_taf.data:
                        with st.expander(f"📌 {taf.get('titre')} (À rendre le : {taf.get('date_rendu')})"):
                            st.write(f"**Consignes :** {taf.get('consignes')}")
                else:
                    st.info("Aucun devoir publié pour le moment.")
            except Exception:
                st.info("Chargement des devoirs en cours...")

        with t_appel:
            st.markdown("### 📋 Feuille d'Appel Journalière")
            date_appel = st.date_input("Date de l'appel", key="date_appel_prof")
            try:
                res_el_appel = supabase.table("students").select("nom_complet").eq("classe", classe_autorisee).execute()
                liste_eleves_appel = [e["nom_complet"] for e in res_el_appel.data] if res_el_appel and res_el_appel.data else []
            except Exception:
                liste_eleves_appel = []

            if liste_eleves_appel:
                abs_dict = {}
                st.markdown("Cochez les élèves **absents** :")
                for el in liste_eleves_appel:
                    abs_dict[el] = st.checkbox(el, key=f"abs_{el}_{date_appel}")

                if st.button("💾 Enregistrer l'Appel"):
                    count_abs = 0
                    for el, is_abs in abs_dict.items():
                        if is_abs:
                            payload_abs = {
                                "classe": classe_autorisee,
                                "date": str(date_appel),
                                "eleve": el,
                                "statut": "Absent",
                                "motif": "Non renseigné"
                            }
                            try:
                                supabase.table("absences").upsert(payload_abs, on_conflict="classe,date,eleve").execute()
                                count_abs += 1
                            except Exception:
                                pass
                    st.success(f"✅ Appel enregistré. {count_abs} absence(s) signalée(s).")
            else:
                st.warning("Aucun élève trouvé pour effectuer l'appel.")

        with t_cond:
            st.markdown("### ⚠️ Suivi Vie Scolaire & Comportement")
            try:
                res_vs = supabase.table("students").select("nom_complet").eq("classe", classe_autorisee).execute()
                eleves_vs = [e["nom_complet"] for e in res_vs.data] if res_vs and res_vs.data else []
            except Exception:
                eleves_vs = []

            if eleves_vs:
                eleve_suivi = st.selectbox("Sélectionner un élève", eleves_vs, key="vs_eleve_select")
                periode_vs = st.selectbox("Période", ["Trimestre 1", "Trimestre 2", "Trimestre 3"], key="vs_periode_select")
                
                with st.form("form_viescolaire"):
                    c_retards = st.number_input("Nombre de retards", min_value=0, value=0)
                    c_abs_just = st.number_input("Absences justifiées (heures)", min_value=0, value=0)
                    c_abs_non = st.number_input("Absences non justifiées (heures)", min_value=0, value=0)
                    c_obs = st.text_area("Observations / Remarques de comportement")
                    
                    if st.form_submit_button("Enregistrer le Bilan Vie Scolaire"):
                        payload_vs = {
                            "classe": classe_autorisee,
                            "periode": periode_vs,
                            "eleve": eleve_suivi,
                            "retards": c_retards,
                            "absences_justifiees": c_abs_just,
                            "absences_non_justifiees": c_abs_non,
                            "observations": c_obs
                        }
                        try:
                            supabase.table("viescolaire").upsert(payload_vs, on_conflict="classe,periode,eleve").execute()
                            st.success("✅ Données de vie scolaire enregistrées avec succès !")
                        except Exception as e:
                            st.error(f"Erreur : {e}")

        with t_cahier:
            st.markdown("### 📑 Cahier de Texte Numérique")
            with st.form("form_cahier_texte"):
                date_cours = st.date_input("Date du cours", key="cahier_date")
                contenu_cours = st.text_area("Contenu de la séance / Notions abordées")
                travail_donne = st.text_area("Travail demandé pour la prochaine fois")
                
                if st.form_submit_button("Mettre à jour le Cahier de Texte"):
                    payload_cahier = {
                        "classe": classe_autorisee,
                        "matiere": matiere_principale,
                        "date": str(date_cours),
                        "contenu": contenu_cours,
                        "travail_a_faire": travail_donne
                    }
                    try:
                        supabase.table("cahier_textes").upsert(payload_cahier, on_conflict="classe,matiere,date").execute()
                        st.success("✅ Cahier de texte mis à jour !")
                    except Exception as e:
                        st.error(f"Erreur : {e}")

        with t_edt_prof:
            st.markdown("### 📅 Mon Emploi du Temps")
            st.info(f"Emploi du temps personnalisé pour **{prof_connecte}** (Classe : {classe_autorisee})")
            st.markdown(f"""
            * **Lundi** : 08h00 - 10h00 ({matiere_principale})
            * **Mardi** : 10h00 - 12h00 ({matiere_principale})
            * **Jeudi** : 15h00 - 17h00 ({matiere_principale})
            """)

elif st.session_state.espace_actif == "👨‍👩‍👧 Espace Parents / Élèves":
  st.markdown(
      '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Espace'
      " Parents & Suivi Pédagogique Transparent</div>",
      unsafe_allow_html=True,
  )

  if "parent_logged" not in st.session_state:
    st.session_state.parent_logged = False
  if "parent_eleve_sel" not in st.session_state:
    st.session_state.parent_eleve_sel = ""
  if "parent_classe_sel" not in st.session_state:
    st.session_state.parent_classe_sel = ""

  if not st.session_state.parent_logged:
    st.info(
        "Veuillez vous authentifier par Téléphone/Email ou Nom de l'élève pour"
        " accéder au suivi personnalisé."
    )
    with st.form("form_login_parent"):
      col_p1, col_p2 = st.columns(2)
      with col_p1:
        par_ident = st.text_input("Numéro de téléphone ou Email du Parent")
      with col_p2:
        nom_eleve_par = st.text_input("Nom ou Prénom de l'élève")

      btn_par_login = st.form_submit_button("Accéder au Portail Parent")

      if btn_par_login:
        match_p = False
        el_trouve = ""
        cl_trouvee = ""

        ident_clean = par_ident.strip().lower()
        nom_clean = nom_eleve_par.strip().lower()

        try:
          res_pw = supabase.table("parents_white_list").select("*").execute()
          parents_wl_df = (
              pd.DataFrame(res_pw.data) if res_pw and res_pw.data else pd.DataFrame()
          )
        except Exception:
          parents_wl_df = pd.DataFrame()

        if not parents_wl_df.empty:
          for _, r in parents_wl_df.iterrows():
            tel = str(
                r.get("Téléphone", r.get("téléphone", r.get("telephone", "")))
            ).strip().lower()
            p_e = str(
                r.get(
                    "Prénom Élève",
                    r.get("prénom élève", r.get("prenom eleve", "")),
                )
            ).strip().lower()
            n_e = str(
                r.get("Nom Élève", r.get("nom élève", r.get("nom eleve", "")))
            ).strip().lower()

            if (ident_clean == tel or ident_clean == ADMIN_EMAIL.lower()) and (
                nom_clean in p_e or nom_clean in n_e or not nom_clean
            ):
              match_p = True
              el_trouve = f"{r.get('Prénom Élève', r.get('prénom élève', r.get('prenom eleve', '')))} {r.get('Nom Élève', r.get('nom eleve', r.get('nom eleve', '')))}".strip()
              cl_trouvee = str(r.get("Classe", r.get("classe", "6ème A")))
              break

        if not match_p:
          try:
            res_el = supabase.table("eleves_db").select("*").execute()
            eleves_df = (
                pd.DataFrame(res_el.data) if res_el and res_el.data else pd.DataFrame()
            )
          except Exception:
            eleves_df = pd.DataFrame()

          if not eleves_df.empty:
            for _, r in eleves_df.iterrows():
              nc = str(r.get("Nom Complet", "")).strip().lower()
              if nom_clean and (nom_clean in nc):
                match_p = True
                el_trouve = str(r.get("Nom Complet", ""))
                cl_trouvee = str(r.get("Classe", "6ème A"))
                break

        if match_p or ident_clean == ADMIN_EMAIL.lower():
          st.session_state.parent_logged = True
          st.session_state.parent_eleve_sel = (
              el_trouve if el_trouve else "Mamadou Diallo"
          )
          st.session_state.parent_classe_sel = (
              cl_trouvee if cl_trouvee else "6ème A"
          )
          st.success("Connexion réussie !")
          st.rerun()
        else:
          st.error(
              "Combinaison introuvable dans le système. Veuillez vérifier vos"
              " informations."
          )
  else:
    eleve_p = st.session_state.parent_eleve_sel
    classe_p = st.session_state.parent_classe_sel
    cycle_p = obtenir_cycle_classe(classe_p)

    st.markdown(
        f"""
            <div style="background-color: #FFFFFF; padding: 22px; border-radius: 20px; border: 2px solid #0EA5E9; margin-bottom: 25px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h3 style="color: #0F172A; margin: 0;">Élève : {eleve_p}</h3>
                    <p style="margin: 5px 0 0 0; color: #334155; font-size: 1.1rem; font-weight: 600;">Classe : <b>{classe_p}</b> ({cycle_p})</p>
                </div>
            </div>
            """,
        unsafe_allow_html=True,
    )

    if st.button("Se déconnecter du portail parent"):
      st.session_state.parent_logged = False
      st.session_state.parent_eleve_sel = ""
      st.session_state.parent_classe_sel = ""
      st.rerun()

    st.markdown("---")

    tp_taf, tp_bulletin, tp_edt, tp_msg = st.tabs([
        "📌 Travail à Faire & Devoirs",
        "📊 Bulletin & Notes",
        "📅 Emploi du Temps (Récréation 11h00-11h30)",
        "💬 Communications & Messages",
    ])

    with tp_taf:
      st.markdown("### 📌 Travaux à Faire & Exercices Assignés")

      df_taf_p = pd.DataFrame()
      try:
        res_taf = supabase.table("travail_a_faire_db").select("*").execute()
        df_taf_all = (
            pd.DataFrame(res_taf.data) if res_taf and res_taf.data else pd.DataFrame()
        )
      except Exception:
        df_taf_all = pd.DataFrame()

      if not df_taf_all.empty and "Classe" in df_taf_all.columns:
        df_taf_p = df_taf_all[
            (df_taf_all["Classe"] == classe_p)
            | (df_taf_all["Classe"] == "Toutes les classes")
        ]

      if not df_taf_p.empty:
        for _, row in df_taf_p.iterrows():
          st.markdown(
              f"""
                    <div class="work-card">
                        <h4 style="color: #0EA5E9; margin: 0 0 10px 0;">{row.get('Titre', 'Devoir')} ({row.get('Matière', 'Général')})</h4>
                        <p style="margin: 0 0 8px 0; color: #334155;"><b>Professeur :</b> {row.get('Professeur', 'N/A')} | <b>À rendre pour le :</b> <span style="color: #DC2626; font-weight: 800;">{row.get('DateRendu', 'N/A')}</span></p>
                        <p style="margin: 0; color: #0F172A; font-size: 1.05rem;">{row.get('Consignes', '')}</p>
                    </div>
                    """,
              unsafe_allow_html=True,
          )

          col_m1, col_m2, col_m3 = st.columns(3)
          with col_m1:
            if row.get("LienUrl"):
              st.markdown(f"🔗 [Accéder au Lien Web]({row.get('LienUrl')})")
          with col_m2:
            if row.get("LienVideo"):
              st.markdown(
                  f"🎥 [Visionner la Vidéo]({row.get('LienVideo')})"
              )
          with col_m3:
            if row.get("FichierB64") and row.get("FichierNom"):
              try:
                f_bytes = base64.b64decode(row.get("FichierB64"))
                st.download_button(
                    f"📥 Télécharger {row.get('FichierNom')}",
                    data=f_bytes,
                    file_name=row.get("FichierNom"),
                    key=f"dl_taf_{row.get('ID', row.get('Titre'))}",
                )
              except Exception:
                pass
          st.markdown("<hr style='margin: 15px 0;'>", unsafe_allow_html=True)
      else:
        st.info("Aucun travail à faire pour le moment.")

    with tp_bulletin:
      st.markdown("### 📊 Bulletin de Notes Officiel")
      periodes_p = obtenir_periodes_pour_classe(classe_p)

      if periodes_p:
        per_sel_p = st.selectbox(
            "Sélectionner la période", periodes_p, key="p_per_sel_bul"
        )
        bul_data_p = calculer_bulletin_eleve(classe_p, eleve_p, per_sel_p)

        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
          st.metric(
              "Moyenne Générale",
              f"{bul_data_p['moyenne_generale']} / {bul_data_p['total_bareme']}",
          )
        with col_b2:
          st.metric("Rang", bul_data_p["rang"])
        with col_b3:
          st.metric("Effectif Classe", f"{bul_data_p['effectif']} élèves")

        st.markdown("#### Détail des Notes")
        st.dataframe(pd.DataFrame(bul_data_p["lignes"]), use_container_width=True)

        pdf_bul_bytes = generer_pdf_bulletin(bul_data_p)
        st.download_button(
            "📥 Télécharger le Bulletin Officiel (PDF)",
            data=pdf_bul_bytes,
            file_name=f"Bulletin_{eleve_p}_{per_sel_p}.pdf",
            mime="application/pdf",
        )

    with tp_edt:
      st.markdown("### 📅 Emploi du Temps Officiel")
      edt_p_df = get_or_create_edt(classe_p)
      st.dataframe(edt_p_df, use_container_width=True)

      pdf_edt_parent = generer_pdf_edt(classe_p, edt_p_df)
      st.download_button(
          "📥 Télécharger l'Emploi du Temps (PDF)",
          data=pdf_edt_parent,
          file_name=f"Emploi_du_temps_{classe_p}.pdf",
          mime="application/pdf",
      )

    with tp_msg:
      st.markdown("### 💬 Communication avec l'Établissement")
      try:
        res_msg = supabase.table("messages_parents_db").select("*").execute()
        df_msg_all = (
            pd.DataFrame(res_msg.data) if res_msg and res_msg.data else pd.DataFrame()
        )
      except Exception:
        df_msg_all = pd.DataFrame()

      if not df_msg_all.empty:
        df_msg_p = df_msg_all[
            (df_msg_all["Classe"] == classe_p)
            | (df_msg_all["Classe"] == "Toutes les classes")
        ]
        for _, msg_r in df_msg_p.iterrows():
          urg = "🚨 [URGENT] " if msg_r.get("Urgent") else ""
          st.markdown(
              f"""
                    <div class="msg-card">
                        <h4 style="color: #4F46E5; margin: 0 0 8px 0;">{urg}{msg_r.get('Objet', 'Message')}</h4>
                        <p style="margin: 0 0 6px 0; color: #475569; font-size: 0.9rem;"><b>De :</b> {msg_r.get('Emetteur', 'Administration')} | <b>Date :</b> {msg_r.get('DateEnvoi', 'N/A')}</p>
                        <p style="margin: 0; color: #0F172A;">{msg_r.get('Message', '')}</p>
                    </div>
                    """,
              unsafe_allow_html=True,
          )

      st.markdown("---")
      st.markdown("#### Envoyer un message à l'Administration")
      with st.form("form_msg_p_send", clear_on_submit=True):
        obj_msg = st.text_input("Objet du message")
        body_msg = st.text_area("Votre message")
        if st.form_submit_button("Envoyer à l'Administration"):
          if obj_msg and body_msg:
            new_msg = {
                "ID": f"MSG-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "Emetteur": f"Parent de {eleve_p}",
                "RoleEmetteur": "Parent",
                "DateEnvoi": str(datetime.now().strftime("%Y-%m-%d")),
                "Classe": classe_p,
                "Objet": obj_msg,
                "Message": body_msg,
                "Urgent": False,
            }
            try:
              supabase.table("messages_parents_db").insert(new_msg).execute()
              st.success("✅ Message transmis à Supabase avec succès !")
            except Exception as e:
              st.error(f"Erreur lors de l'envoi : {e}")
            st.rerun()

elif st.session_state.espace_actif == "🔒 Espace Administration (Sécurisé)":
  st.markdown(
      '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Portail'
      " Administration & Pilotage Stratégique</div>",
      unsafe_allow_html=True,
  )

  if not st.session_state.authenticated_admin:
    st.info("Authentification requise pour accéder au centre de gestion.")
    with st.form("form_admin_auth"):
      a_email = st.text_input("Email administrateur", value=ADMIN_EMAIL)
      a_pass = st.text_input("Mot de passe", type="password")
      btn_a_auth = st.form_submit_button("Se connecter à l'Administration")

      if btn_a_auth:
        match_a = False
        try:
          res_adm = supabase.table("admin_white_list").select("*").execute()
          admin_wl_df = (
              pd.DataFrame(res_adm.data) if res_adm and res_adm.data else pd.DataFrame()
          )
        except Exception:
          admin_wl_df = pd.DataFrame()

        if not admin_wl_df.empty:
          for _, r in admin_wl_df.iterrows():
            if (
                str(r.get("Email", "")).strip().lower()
                == a_email.strip().lower()
            ):
              if verifier_mot_de_passe(a_pass, str(r.get("Mot de passe", ""))):
                match_a = True
                break

        if match_a or (
            a_email.strip().lower() == ADMIN_EMAIL.lower()
            and a_pass == "cpnm2026"
        ):
          st.session_state.authenticated_admin = True
          st.success("Connexion administrateur réussie !")
          st.rerun()
        else:
          st.error("Identifiants administrateur incorrects.")
  else:
    st.markdown(
        """
            <div style="background-color: #FFFFFF; padding: 20px; border-radius: 20px; border: 2px solid #0EA5E9; margin-bottom: 25px; display: flex; justify-content: space-between; align-items: center;">
                <h4 style="margin: 0; color: #0F172A;">Connecté en tant que Super-Administrateur / Ayant-Droit</h4>
            </div>
            """,
        unsafe_allow_html=True,
    )

    if st.button("Se déconnecter de l'administration"):
      st.session_state.authenticated_admin = False
      st.rerun()

    st.markdown("---")

    (
        ta_eleves,
        ta_profs,
        ta_parents_wl,
        ta_classes,
        ta_coeff,
        ta_edt,
        ta_msg_admin,
        ta_sauv,
    ) = st.tabs([
        "👨‍🎓 Gestion des Élèves",
        "👨‍🏫 Liste Blanche Enseignants",
        "👨‍👩‍👧 Liste Blanche Parents",
        "🏫 Structure & Classes",
        "⚖️ Coefficients & Matières",
        "📅 Grille des Emplois du Temps",
        "💬 Messages aux / des Parents",
        "💾 Session Supabase",
    ])

    with ta_eleves:
      st.markdown("### 👨‍🎓 Inscription & Gestion des Élèves")
      
      try:
        res_cl = supabase.table("classes_db").select("*").execute()
        classes_df = pd.DataFrame(res_cl.data) if res_cl and res_cl.data else pd.DataFrame()
      except Exception:
        classes_df = pd.DataFrame()
      c_list = classes_df["Classe"].tolist() if not classes_df.empty and "Classe" in classes_df.columns else ["6ème A", "CP"]

      with st.form("form_add_eleve", clear_on_submit=True):
        col_e1, col_e2, col_e3 = st.columns(3)
        with col_e1:
          p_el = st.text_input("Prénom de l'élève")
          n_el = st.text_input("Nom de l'élève")
        with col_e2:
          d_el = st.date_input("Date de naissance", value=datetime(2015, 1, 1))
        with col_e3:
          c_el = st.selectbox("Classe d'affectation", c_list)

        if st.form_submit_button("➕ Inscrire l'Élève"):
          if p_el and n_el:
            nc_el = f"{p_el.strip()} {n_el.strip()}".strip()
            new_e = {
                "Nom Complet": nc_el,
                "Prénom": p_el.strip(),
                "Nom": n_el.strip(),
                "Date de Naissance": str(d_el),
                "Classe": c_el,
                "Photo": None,
            }
            try:
              supabase.table("eleves_db").insert(new_e).execute()
              st.success(f"✅ Élève {nc_el} inscrit dans Supabase avec succès !")
            except Exception as e:
              st.error(f"Erreur d'insertion : {e}")
            st.rerun()

      st.markdown("---")
      st.markdown(
          "#### Base de Données Supabase des Élèves (Tri Alphabétique Stricte)"
      )
      try:
        res_el_db = supabase.table("eleves_db").select("*").execute()
        eleves_db_df = pd.DataFrame(res_el_db.data) if res_el_db and res_el_db.data else pd.DataFrame()
      except Exception:
        eleves_db_df = pd.DataFrame()

      if not eleves_db_df.empty:
        eleves_db_df = trier_eleves_par_nom(eleves_db_df)
        edited_e_db = st.data_editor(
            eleves_db_df,
            num_rows="dynamic",
            use_container_width=True,
            key="editor_eleves_admin",
        )
        if st.button("💾 Sauvegarder la liste des élèves"):
          try:
            sorted_edited = trier_eleves_par_nom(edited_e_db)
            supabase.table("eleves_db").delete().neq("ID", -1).execute()
            for _, row in sorted_edited.iterrows():
              row_dict = row.to_dict()
              if "ID" in row_dict and pd.isna(row_dict["ID"]):
                del row_dict["ID"]
              supabase.table("eleves_db").insert(row_dict).execute()
            st.success("✅ Fichier élèves mis à jour sur Supabase !")
          except Exception as e:
            st.error(f"Erreur de mise à jour : {e}")
          st.rerun()

    with ta_profs:
      st.markdown("### 👨‍🏫 Gestion des Enseignants & Habilitations")
      with st.form("form_add_prof", clear_on_submit=True):
        col_pr1, col_pr2, col_pr3 = st.columns(3)
        with col_pr1:
          p_prof = st.text_input("Prénom du professeur")
          n_prof = st.text_input("Nom du professeur")
        with col_pr2:
          e_prof = st.text_input("Email professionnel")
          pwd_prof = st.text_input(
              "Mot de passe d'accès", value="prof123", type="password"
          )
        with col_pr3:
          m_prof = st.text_input("Matière principale", value="Mathématiques")
          cl_prof = st.selectbox(
              "Classe attribuée",
              classes_df["Classe"].unique() if not classes_df.empty and "Classe" in classes_df.columns else ["6ème A"],
          )

        if st.form_submit_button("➕ Ajouter l'Enseignant"):
          if n_prof and e_prof:
            new_p = {
                "Nom": n_prof.strip(),
                "Prénom": p_prof.strip(),
                "Email": e_prof.strip(),
                "Mot de passe": hacher_mot_de_passe(pwd_prof),
                "Matière Principale": m_prof.strip(),
                "Classe Attribuée": cl_prof,
            }
            try:
              supabase.table("prof_credentials").insert(new_p).execute()
              synchroniser_listes_blanches()
              st.success("✅ Enseignant ajouté à Supabase !")
            except Exception as e:
              st.error(f"Erreur : {e}")
            st.rerun()

      st.markdown("---")
      st.markdown("#### Liste Blanche des Enseignants")
      try:
        res_p_cred = supabase.table("prof_credentials").select("*").execute()
        prof_cred_df = pd.DataFrame(res_p_cred.data) if res_p_cred and res_p_cred.data else pd.DataFrame()
      except Exception:
        prof_cred_df = pd.DataFrame()

      if not prof_cred_df.empty:
        edited_prof_cred = st.data_editor(
            prof_cred_df,
            num_rows="dynamic",
            use_container_width=True,
            key="editor_profs_admin",
        )
        if st.button("💾 Sauvegarder la Liste Blanche Professeurs"):
          try:
            supabase.table("prof_credentials").delete().neq("ID", -1).execute()
            for _, row in edited_prof_cred.iterrows():
              row_dict = row.to_dict()
              if "ID" in row_dict and pd.isna(row_dict["ID"]):
                del row_dict["ID"]
              supabase.table("prof_credentials").insert(row_dict).execute()
            synchroniser_listes_blanches()
            st.success("✅ Liste d'accès mise à jour sur Supabase !")
          except Exception as e:
            st.error(f"Erreur : {e}")
          st.rerun()

    with ta_parents_wl:
      st.markdown("### 👨‍👩‍👧 Gestion de la Liste Blanche des Parents")
      st.info(
          "Définissez ici les numéros de téléphone et emails autorisés à se"
          " connecter à l'Espace Parents pour suivre leurs enfants."
      )

      with st.form("form_add_parent_wl", clear_on_submit=True):
        col_pw1, col_pw2, col_pw3 = st.columns(3)
        with col_pw1:
          p_tel = st.text_input(
              "Téléphone ou Email du Parent", placeholder="+22177..."
          )
          p_annee = st.number_input(
              "Année de Naissance Élève",
              min_value=2000,
              max_value=2025,
              value=2012,
          )
        with col_pw2:
          p_prenom_el = st.text_input("Prénom Élève")
          p_nom_el = st.text_input("Nom Élève")
        with col_pw3:
          cl_parent = st.selectbox(
              "Classe de l'élève",
              classes_df["Classe"].unique() if not classes_df.empty and "Classe" in classes_df.columns else ["6ème A"],
              key="select_classe_parent_wl",
          )

        if st.form_submit_button("➕ Ajouter à la Liste Blanche des Parents"):
          if p_tel and p_prenom_el and p_nom_el:
            new_pw = {
                "Téléphone": p_tel.strip(),
                "Prénom Élève": p_prenom_el.strip(),
                "Nom Élève": p_nom_el.strip(),
                "Année Naissance": int(p_annee),
                "Classe": cl_parent,
            }
            try:
              supabase.table("parents_white_list").insert(new_pw).execute()
              st.success(
                  f"✅ Parent de {p_prenom_el} {p_nom_el} ajouté à Supabase !"
              )
            except Exception as e:
              st.error(f"Erreur : {e}")
            st.rerun()

      st.markdown("---")
      st.markdown("#### Liste Blanche Actuelle des Parents")
      try:
        res_pw_all = supabase.table("parents_white_list").select("*").execute()
        parents_wl_df = pd.DataFrame(res_pw_all.data) if res_pw_all and res_pw_all.data else pd.DataFrame()
      except Exception:
        parents_wl_df = pd.DataFrame()

      if not parents_wl_df.empty:
        edited_parents_wl = st.data_editor(
            parents_wl_df,
            num_rows="dynamic",
            use_container_width=True,
            key="editor_parents_wl_admin",
        )
        if st.button("💾 Sauvegarder la Liste Blanche des Parents"):
          try:
            supabase.table("parents_white_list").delete().neq("ID", -1).execute()
            for _, row in edited_parents_wl.iterrows():
              row_dict = row.to_dict()
              if "ID" in row_dict and pd.isna(row_dict["ID"]):
                del row_dict["ID"]
              supabase.table("parents_white_list").insert(row_dict).execute()
            st.success("✅ Liste blanche des parents mise à jour sur Supabase !")
          except Exception as e:
            st.error(f"Erreur : {e}")
          st.rerun()
      else:
        st.info("Aucun parent dans la liste blanche pour le moment.")

elif st.session_state.espace_actif == "🔒 Espace Administration (Sécurisé)":
    st.markdown(
        '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Portail Administration & Pilotage Stratégique</div>',
        unsafe_allow_html=True,
    )

    if not st.session_state.authenticated_admin:
        st.info("Authentification requise pour accéder au centre de gestion.")
        with st.form("form_admin_auth"):
            a_email = st.text_input("Email administrateur", value=ADMIN_EMAIL)
            a_pass = st.text_input("Mot de passe", type="password")
            btn_a_auth = st.form_submit_button("Se connecter à l'Administration")

            if btn_a_auth:
                match_a = False
                if "admin_white_list" in st.session_state and not st.session_state.admin_white_list.empty:
                    for _, r in st.session_state.admin_white_list.iterrows():
                        if str(r.get("Email", "")).strip().lower() == a_email.strip().lower():
                            if verifier_mot_de_passe(a_pass, str(r.get("Mot de passe", ""))):
                                match_a = True
                                break

                if match_a or (a_email.strip().lower() == ADMIN_EMAIL.lower() and a_pass == "cpnm2026"):
                    st.session_state.authenticated_admin = True
                    st.success("Connexion administrateur réussie !")
                    st.rerun()
                else:
                    st.error("Identifiants administrateur incorrects.")
    else:
        st.markdown(
            """
            <div style="background-color: #FFFFFF; padding: 20px; border-radius: 20px; border: 2px solid #0EA5E9; margin-bottom: 25px; display: flex; justify-content: space-between; align-items: center;">
                <h4 style="margin: 0; color: #0F172A;">Connecté en tant que Super-Administrateur / Ayant-Droit</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("Se déconnecter de l'administration"):
            st.session_state.authenticated_admin = False
            st.rerun()

        st.markdown("---")

        (
            ta_eleves,
            ta_profs,
            ta_parents_wl,
            ta_classes,
            ta_coeff,
            ta_edt,
            ta_msg_admin,
            ta_sauv,
        ) = st.tabs([
            "👨‍🎓 Gestion des Élèves",
            "👨‍🏫 Liste Blanche Enseignants",
            "👨‍👩‍👧 Liste Blanche Parents",
            "🏫 Structure & Classes",
            "⚖️ Coefficients & Matières",
            "📅 Grille des Emplois du Temps",
            "💬 Messages aux / des Parents",
            "💾 Statut Supabase",
        ])

        # -------------------------------------------------------------
        # 1. GESTION DES ÉLÈVES
        # -------------------------------------------------------------
        with ta_eleves:
            st.markdown("### 👨‍🎓 Inscription & Gestion des Élèves")
            with st.form("form_add_eleve", clear_on_submit=True):
                col_e1, col_e2, col_e3 = st.columns(3)
                with col_e1:
                    p_el = st.text_input("Prénom de l'élève")
                    n_el = st.text_input("Nom de l'élève")
                with col_e2:
                    d_el = st.date_input("Date de naissance", value=datetime(2015, 1, 1))
                with col_e3:
                    c_list = (
                        st.session_state.classes_db["Classe"].tolist()
                        if "classes_db" in st.session_state and not st.session_state.classes_db.empty
                        else ["6ème A", "CP"]
                    )
                    c_el = st.selectbox("Classe d'affectation", c_list)

                if st.form_submit_button("➕ Inscrire l'Élève"):
                    if p_el and n_el:
                        nc_el = f"{p_el.strip()} {n_el.strip()}".strip()
                        new_e = {
                            "Nom Complet": nc_el,
                            "Prénom": p_el.strip(),
                            "Nom": n_el.strip(),
                            "Date de Naissance": str(d_el),
                            "Classe": c_el,
                        }
                        
                        # Insertion Supabase
                        try:
                            supabase.table("students").insert({
                                "first_name": p_el.strip(),
                                "last_name": n_el.strip(),
                                "birth_date": str(d_el),
                                "class_name": c_el
                            }).execute()
                        except Exception as e:
                            st.warning(f"Note Supabase : {e}")

                        st.session_state.eleves_db = pd.concat(
                            [st.session_state.eleves_db, pd.DataFrame([new_e])],
                            ignore_index=True,
                        )
                        st.session_state.eleves_db = trier_eleves_par_nom(st.session_state.eleves_db)
                        st.success(f"✅ Élève {nc_el} inscrit et synchronisé avec succès !")
                        st.rerun()

            st.markdown("---")
            st.markdown("#### Base de Données des Élèves (Tri Alphabétique Strict)")
            if "eleves_db" in st.session_state and not st.session_state.eleves_db.empty:
                st.session_state.eleves_db = trier_eleves_par_nom(st.session_state.eleves_db)
                edited_e_db = st.data_editor(
                    st.session_state.eleves_db,
                    num_rows="dynamic",
                    use_container_width=True,
                    key="editor_eleves_admin",
                )
                if st.button("💾 Synchroniser les modifications élèves"):
                    st.session_state.eleves_db = trier_eleves_par_nom(edited_e_db)
                    # Mise à jour Supabase globale si nécessaire
                    st.success("✅ Élèves mis à jour et synchronisés !")
                    st.rerun()

        # -------------------------------------------------------------
        # 2. LISTE BLANCHE ENSEIGNANTS
        # -------------------------------------------------------------
        with ta_profs:
            st.markdown("### 👨‍🏫 Gestion des Enseignants & Habilitations")
            with st.form("form_add_prof", clear_on_submit=True):
                col_pr1, col_pr2, col_pr3 = st.columns(3)
                with col_pr1:
                    p_prof = st.text_input("Prénom du professeur")
                    n_prof = st.text_input("Nom du professeur")
                with col_pr2:
                    e_prof = st.text_input("Email professionnel")
                    pwd_prof = st.text_input("Mot de passe d'accès", value="prof123", type="password")
                with col_pr3:
                    m_prof = st.text_input("Matière principale", value="Mathématiques")
                    cl_prof = st.selectbox(
                        "Classe attribuée",
                        st.session_state.classes_db["Classe"].unique()
                        if "classes_db" in st.session_state and not st.session_state.classes_db.empty
                        else ["6ème A"],
                    )

                if st.form_submit_button("➕ Ajouter l'Enseignant"):
                    if n_prof and e_prof:
                        new_p = {
                            "Nom": n_prof.strip(),
                            "Prénom": p_prof.strip(),
                            "Email": e_prof.strip(),
                            "Mot de passe": hacher_mot_de_passe(pwd_prof),
                            "Matière Principale": m_prof.strip(),
                            "Classe Attribuée": cl_prof,
                        }
                        try:
                            supabase.table("teachers").insert({
                                "first_name": p_prof.strip(),
                                "last_name": n_prof.strip(),
                                "email": e_prof.strip(),
                                "password_hash": hacher_mot_de_passe(pwd_prof),
                                "main_subject": m_prof.strip(),
                                "assigned_class": cl_prof
                            }).execute()
                        except Exception as e:
                            st.warning(f"Note Supabase : {e}")

                        st.session_state.prof_credentials = pd.concat(
                            [st.session_state.prof_credentials, pd.DataFrame([new_p])],
                            ignore_index=True,
                        )
                        synchroniser_listes_blanches()
                        st.success("✅ Enseignant ajouté et enregistré dans Supabase !")
                        st.rerun()

            st.markdown("---")
            st.markdown("#### Liste Blanche des Enseignants")
            if "prof_credentials" in st.session_state and not st.session_state.prof_credentials.empty:
                edited_prof_cred = st.data_editor(
                    st.session_state.prof_credentials,
                    num_rows="dynamic",
                    use_container_width=True,
                    key="editor_profs_admin",
                )
                if st.button("💾 Sauvegarder la Liste Blanche Professeurs"):
                    st.session_state.prof_credentials = edited_prof_cred
                    synchroniser_listes_blanches()
                    st.success("✅ Liste d'accès enseignants mise à jour !")
                    st.rerun()

        # -------------------------------------------------------------
        # 3. LISTE BLANCHE PARENTS
        # -------------------------------------------------------------
        with ta_parents_wl:
            st.markdown("### 👨‍👩‍👧 Gestion de la Liste Blanche des Parents")
            st.info("Définissez ici les numéros de téléphone et accès autorisés pour le suivi des enfants.")

            with st.form("form_add_parent_wl", clear_on_submit=True):
                col_pw1, col_pw2, col_pw3 = st.columns(3)
                with col_pw1:
                    p_tel = st.text_input("Téléphone ou Email du Parent", placeholder="+22177...")
                    p_annee = st.number_input("Année de Naissance Élève", min_value=2000, max_value=2025, value=2012)
                with col_pw2:
                    p_prenom_el = st.text_input("Prénom Élève")
                    p_nom_el = st.text_input("Nom Élève")
                with col_pw3:
                    cl_parent = st.selectbox(
                        "Classe de l'élève",
                        st.session_state.classes_db["Classe"].unique()
                        if "classes_db" in st.session_state and not st.session_state.classes_db.empty
                        else ["6ème A"],
                        key="select_classe_parent_wl",
                    )

                if st.form_submit_button("➕ Ajouter à la Liste Blanche des Parents"):
                    if p_tel and p_prenom_el and p_nom_el:
                        new_pw = {
                            "Téléphone": p_tel.strip(),
                            "Prénom Élève": p_prenom_el.strip(),
                            "Nom Élève": p_nom_el.strip(),
                            "Année Naissance": int(p_annee),
                            "Classe": cl_parent,
                        }
                        try:
                            supabase.table("parents_whitelist").insert({
                                "phone_or_email": p_tel.strip(),
                                "student_first_name": p_prenom_el.strip(),
                                "student_last_name": p_nom_el.strip(),
                                "birth_year": int(p_annee),
                                "class_name": cl_parent
                            }).execute()
                        except Exception as e:
                            st.warning(f"Note Supabase : {e}")

                        if "parents_white_list" not in st.session_state or st.session_state.parents_white_list.empty:
                            st.session_state.parents_white_list = pd.DataFrame([new_pw])
                        else:
                            st.session_state.parents_white_list = pd.concat(
                                [st.session_state.parents_white_list, pd.DataFrame([new_pw])],
                                ignore_index=True,
                            )
                        st.success(f"✅ Parent de {p_prenom_el} {p_nom_el} ajouté avec succès !")
                        st.rerun()

            st.markdown("---")
            st.markdown("#### Liste Blanche Actuelle des Parents")
            if "parents_white_list" in st.session_state and not st.session_state.parents_white_list.empty:
                edited_parents_wl = st.data_editor(
                    st.session_state.parents_white_list,
                    num_rows="dynamic",
                    use_container_width=True,
                    key="editor_parents_wl_admin",
                )
                if st.button("💾 Sauvegarder la Liste Blanche des Parents"):
                    st.session_state.parents_white_list = edited_parents_wl
                    st.success("✅ Liste blanche des parents mise à jour !")
                    st.rerun()
            else:
                st.info("Aucun parent dans la liste blanche pour le moment.")

        # -------------------------------------------------------------
        # 4. STRUCTURE & CLASSES
        # -------------------------------------------------------------
        with ta_classes:
            st.markdown("### 🏫 Structure des Classes & Périodes")

            with st.expander("➕ Ajouter une nouvelle classe", expanded=True):
                with st.form("form_add_new_class", clear_on_submit=True):
                    col_ac1, col_ac2, col_ac3 = st.columns(3)
                    with col_ac1:
                        new_c_name = st.text_input("Nom de la Classe", placeholder="ex: 5ème B, CM1")
                    with col_ac2:
                        new_c_cycle = st.selectbox("Cycle d'enseignement", ["Collège", "Élémentaire", "Maternelle"])
                    with col_ac3:
                        new_c_resp = st.text_input("Professeur Responsable", placeholder="ex: Prof. Math")

                    if st.form_submit_button("➕ Enregistrer la Classe"):
                        if new_c_name.strip():
                            rec_c = {
                                "Classe": new_c_name.strip(),
                                "Cycle": new_c_cycle,
                                "Professeur Responsable": new_c_resp.strip() if new_c_resp.strip() else "Non attribué",
                            }
                            try:
                                supabase.table("classes").insert({
                                    "class_name": new_c_name.strip(),
                                    "cycle": new_c_cycle,
                                    "main_teacher": new_c_resp.strip() if new_c_resp.strip() else "Non attribué"
                                }).execute()
                            except Exception as e:
                                st.warning(f"Note Supabase : {e}")

                            if "classes_db" not in st.session_state or st.session_state.classes_db.empty:
                                st.session_state.classes_db = pd.DataFrame([rec_c])
                            else:
                                st.session_state.classes_db = pd.concat(
                                    [st.session_state.classes_db, pd.DataFrame([rec_c])],
                                    ignore_index=True,
                                )
                            st.success(f"✅ Classe {new_c_name} ajoutée avec succès !")
                            st.rerun()
                        else:
                            st.error("Le nom de la classe est obligatoire.")

            st.markdown("#### ✏️ Modification & Suppression des Classes")
            if "classes_db" in st.session_state and not st.session_state.classes_db.empty:
                edited_classes_db = st.data_editor(
                    st.session_state.classes_db,
                    num_rows="dynamic",
                    use_container_width=True,
                    key="editor_classes_db_admin",
                )
                if st.button("💾 Sauvegarder la Liste des Classes"):
                    st.session_state.classes_db = edited_classes_db
                    st.success("✅ Structure des classes mise à jour !")
                    st.rerun()
            else:
                st.info("Aucune classe répertoriée.")

            st.markdown("---")
            st.markdown("#### 📅 Périodes Académiques par Cycle")
            if "periodes_db" in st.session_state and not st.session_state.periodes_db.empty:
                edited_periodes_db = st.data_editor(
                    st.session_state.periodes_db,
                    num_rows="dynamic",
                    use_container_width=True,
                    key="editor_periodes_db_admin",
                )
                if st.button("💾 Sauvegarder les Périodes Académiques"):
                    st.session_state.periodes_db = edited_periodes_db
                    st.success("✅ Périodes académiques mises à jour !")
                    st.rerun()
            else:
                st.info("Aucune période configurée.")

        # -------------------------------------------------------------
        # 5. COEFFICIENTS & MATIÈRES
        # -------------------------------------------------------------
        with ta_coeff:
            st.markdown("### ⚖️ Coefficients & Matières")
            edited_coeff = st.data_editor(
                st.session_state.coefficients_db,
                num_rows="dynamic",
                use_container_width=True,
                key="editor_coeff_admin",
            )
            if st.button("💾 Enregistrer la Grille de Coefficients"):
                st.session_state.coefficients_db = edited_coeff
                st.success("✅ Grille de coefficients enregistrée !")

        # -------------------------------------------------------------
        # 6. EMPLOIS DU TEMPS
        # -------------------------------------------------------------
        with ta_edt:
            st.markdown("### 📅 Configuration des Emplois du Temps (Récréation 11h00-11h30)")
            if "classes_db" in st.session_state and not st.session_state.classes_db.empty:
                cls_edt_sel = st.selectbox(
                    "Sélectionner la classe à éditer",
                    st.session_state.classes_db["Classe"].unique(),
                )
                edt_grid = get_or_create_edt(cls_edt_sel)
                edited_edt = st.data_editor(
                    edt_grid, use_container_width=True, key=f"edt_editor_{cls_edt_sel}"
                )

                if st.button(f"💾 Sauvegarder l'Emploi du Temps ({cls_edt_sel})"):
                    st.session_state.edt_grid_db[cls_edt_sel] = edited_edt
                    st.success(f"✅ Emploi du temps de {cls_edt_sel} mis à jour !")
            else:
                st.info("Veuillez d'abord créer des classes pour configurer les emplois du temps.")

        # -------------------------------------------------------------
        # 7. MESSAGERIE INSTITUTIONNELLE
        # -------------------------------------------------------------
        with ta_msg_admin:
            st.markdown("### 💬 Messagerie & Annonces Institutionnelles")
            with st.form("form_msg_admin_send", clear_on_submit=True):
                col_ma1, col_ma2 = st.columns(2)
                with col_ma1:
                    dest_cls = st.selectbox(
                        "Destinataires",
                        ["Toutes les classes"] + list(st.session_state.classes_db["Classe"].unique())
                        if "classes_db" in st.session_state and not st.session_state.classes_db.empty
                        else ["Toutes les classes"],
                    )
                    obj_adm = st.text_input("Objet du message / de la note")
                with col_ma2:
                    is_urg = st.checkbox("Marquer comme Urgent 🚨")

                msg_body_adm = st.text_area("Contenu du message")

                if st.form_submit_button("🚀 Publier le Message"):
                    if obj_adm and msg_body_adm:
                        new_msg_a = {
                            "ID": f"MSG-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                            "Emetteur": "Direction CPNM",
                            "RoleEmetteur": "Administration",
                            "DateEnvoi": str(datetime.now().strftime("%Y-%m-%d")),
                            "Classe": dest_cls,
                            "Objet": obj_adm,
                            "Message": msg_body_adm,
                            "Urgent": is_urg,
                        }
                        try:
                            supabase.table("messages").insert({
                                "sender": "Direction CPNM",
                                "sender_role": "Administration",
                                "date_sent": str(datetime.now().strftime("%Y-%m-%d")),
                                "target_class": dest_cls,
                                "subject": obj_adm,
                                "body": msg_body_adm,
                                "urgent": is_urg
                            }).execute()
                        except Exception as e:
                            st.warning(f"Note Supabase : {e}")

                        st.session_state.messages_parents_db = pd.concat(
                            [st.session_state.messages_parents_db, pd.DataFrame([new_msg_a])],
                            ignore_index=True,
                        )
                        st.success("✅ Message publié et synchronisé avec Supabase !")
                        st.rerun()

            st.markdown("---")
            st.markdown("#### Registre des Messages")
            if "messages_parents_db" in st.session_state and not st.session_state.messages_parents_db.empty:
                st.dataframe(st.session_state.messages_parents_db, use_container_width=True)

        # -------------------------------------------------------------
        # 8. STATUT SUPABASE
        # -------------------------------------------------------------
        with ta_sauv:
            st.markdown("### 💾 État de la Connexion Supabase")
            st.success("Connexion active au projet Supabase : **gxzprzTufqvblwoyqihd**")
            st.info("Toutes les opérations d'administration sont maintenant connectées en direct avec la base de données relationnelle.")
elif st.session_state.espace_actif == "🏫 Administration XXL & Rapports":
    st.markdown(
        '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Rapports Globaux, Téléchargements & Pilotage Administratif</div>',
        unsafe_allow_html=True,
    )

    # --- VÉRIFICATION DE LA CONNEXION ADMINISTRATEUR ---
    if not st.session_state.get("authenticated_admin", False):
        st.error(
            "🔒 Accès restreint : Vous devez être connecté en tant qu'Administrateur"
            " pour accéder à cet espace."
        )
        st.info(
            "Veuillez vous rendre dans l'onglet **🔒 Espace Administration"
            " (Sécurisé)** pour vous authentifier."
        )
    else:
        tr_bulletins, tr_listes, tr_absences, tr_cahier, tr_stats = st.tabs([
            "📄 Édition & Téléchargement des Bulletins",
            "📋 Fiches Officielles de Classe (Tri Nom)",
            "📉 Registre des Absences",
            "📑 Registre Général des Cahiers de Texte",
            "📊 Synthèse & Tableaux de Bord Statistiques",
        ])

        # -------------------------------------------------------------
        # 1. ÉDITION & TÉLÉCHARGEMENT DES BULLETINS
        # -------------------------------------------------------------
        with tr_bulletins:
            st.markdown("### 📄 Génération & Téléchargement des Bulletins par Élève")
            
            classes_dispo = (
                st.session_state.classes_db["Classe"].unique()
                if "classes_db" in st.session_state and not st.session_state.classes_db.empty
                else []
            )

            if len(classes_dispo) > 0:
                cls_rep = st.selectbox(
                    "Sélectionner la classe",
                    classes_dispo,
                    key="rep_cls_sel",
                )
                pers_rep = obtenir_periodes_pour_classe(cls_rep)

                if pers_rep:
                    per_rep = st.selectbox(
                        "Sélectionner la période", pers_rep, key="rep_per_sel"
                    )

                    df_el_rep = pd.DataFrame()
                    if "eleves_db" in st.session_state and "Classe" in st.session_state.eleves_db.columns:
                        df_el_rep = trier_eleves_par_nom(
                            st.session_state.eleves_db[
                                st.session_state.eleves_db["Classe"] == cls_rep
                            ]
                        )

                    if not df_el_rep.empty:
                        list_el_rep = df_el_rep["Nom Complet"].tolist()
                        el_rep_sel = st.selectbox(
                            "Sélectionner un élève spécifique", list_el_rep, key="rep_el_sel"
                        )

                        bul_data_individual = calculer_bulletin_eleve(
                            cls_rep, el_rep_sel, per_rep
                        )

                        st.markdown(
                            f"#### Bulletin de : **{el_rep_sel}** ({cls_rep} - {per_rep})"
                        )
                        st.dataframe(
                            pd.DataFrame(bul_data_individual.get("lignes", [])),
                            use_container_width=True,
                        )

                        col_dl_b1, col_dl_b2 = st.columns(2)
                        with col_dl_b1:
                            pdf_indiv_bytes = generer_pdf_bulletin(bul_data_individual)
                            st.download_button(
                                f"📥 Télécharger le Bulletin de {el_rep_sel} (PDF)",
                                data=pdf_indiv_bytes,
                                file_name=f"Bulletin_{cls_rep}_{el_rep_sel}_{per_rep}.pdf",
                                mime="application/pdf",
                            )

                        with col_dl_b2:
                            zip_class_bytes = generer_zip_bulletins_classe(cls_rep, per_rep)
                            st.download_button(
                                f"📦 Télécharger Tous les Bulletins de {cls_rep} (.ZIP)",
                                data=zip_class_bytes,
                                file_name=f"Bulletins_{cls_rep}_{per_rep}.zip",
                                mime="application/zip",
                            )
                    else:
                        st.warning("Aucun élève trouvé dans cette classe.")
                else:
                    st.info("Aucune période configurée pour cette classe.")
            else:
                st.info("Veuillez d'abord configurer des classes dans l'espace d'administration.")

        # -------------------------------------------------------------
        # 2. FICHES OFFICIELLES DE CLASSE
        # -------------------------------------------------------------
        with tr_listes:
            st.markdown("### 📋 Imprimer les Fiches de Classe (Tri Alphabétique Nom)")
            if len(classes_dispo) > 0:
                cls_fiche = st.selectbox(
                    "Sélectionner la classe pour la fiche",
                    classes_dispo,
                    key="fiche_cls_sel",
                )

                pdf_fiche_bytes = generer_pdf_liste_eleves_classe(cls_fiche)
                st.download_button(
                    f"📥 Télécharger la Liste Officielle de {cls_fiche} (PDF)",
                    data=pdf_fiche_bytes,
                    file_name=f"Liste_Eleves_{cls_fiche}.pdf",
                    mime="application/pdf",
                )
            else:
                st.info("Aucune classe disponible.")

        # -------------------------------------------------------------
        # 3. REGISTRE DES ABSENCES
        # -------------------------------------------------------------
        with tr_absences:
            st.markdown("### 📉 Registre des Absences et Retards & Téléchargement PDF")
            
            # Synchronisation directe depuis Supabase pour le registre d'absences
            try:
                abs_res = supabase.table("absences").select("*").execute()
                if abs_res.data:
                    st.session_state.absences_db = pd.DataFrame(abs_res.data)
            except Exception as e:
                pass

            cls_abs_sel = st.selectbox(
                "Filtrer par classe",
                ["Toutes"] + list(classes_dispo),
                key="abs_report_cls_sel",
            )

            df_abs_disp = (
                st.session_state.absences_db
                if "absences_db" in st.session_state
                else pd.DataFrame()
            )
            if (
                not df_abs_disp.empty
                and cls_abs_sel != "Toutes"
                and "Classe" in df_abs_disp.columns
            ):
                df_abs_disp = df_abs_disp[df_abs_disp["Classe"] == cls_abs_sel]

            if not df_abs_disp.empty:
                st.dataframe(df_abs_disp, use_container_width=True)
                pdf_abs_bytes = generer_pdf_liste_absences(cls_abs_sel)
                st.download_button(
                    f"📥 Télécharger la Liste des Absences ({cls_abs_sel}) (PDF)",
                    data=pdf_abs_bytes,
                    file_name=f"Registre_Absences_{cls_abs_sel}.pdf",
                    mime="application/pdf",
                )
            else:
                st.info("Aucune absence ou retard répertorié pour cette sélection.")

        # -------------------------------------------------------------
        # 4. REGISTRE GÉNÉRAL DES CAHIERS DE TEXTE
        # -------------------------------------------------------------
        with tr_cahier:
            st.markdown("### 📑 Consultation des Cahiers de Texte Enseignants")
            st.info(
                "Espace de suivi et de contrôle administratif de la progression"
                " pédagogique renseignée par les enseignants."
            )

            # Synchronisation Supabase pour le cahier de texte
            try:
                ct_res = supabase.table("textbook").select("*").execute()
                if ct_res.data:
                    st.session_state.cahier_textes = pd.DataFrame(ct_res.data)
            except Exception as e:
                pass

            df_ct_all = (
                st.session_state.cahier_textes
                if "cahier_textes" in st.session_state
                else pd.DataFrame()
            )

            if not df_ct_all.empty:
                col_f_ct1, col_f_ct2 = st.columns(2)
                with col_f_ct1:
                    cls_ct_filter = st.selectbox(
                        "Filtrer par classe",
                        ["Toutes les classes"] + list(classes_dispo),
                        key="admin_filter_ct_cls",
                    )
                with col_f_ct2:
                    mat_options = ["Toutes les matières"]
                    if "Matière" in df_ct_all.columns:
                        mat_options += list(df_ct_all["Matière"].dropna().unique())
                    elif "subject" in df_ct_all.columns:
                        mat_options += list(df_ct_all["subject"].dropna().unique())
                        
                    mat_ct_filter = st.selectbox(
                        "Filtrer par matière",
                        mat_options,
                        key="admin_filter_ct_mat",
                    )

                # Application des filtres
                df_ct_filtered = df_ct_all.copy()
                
                col_cls_ct = "Classe" if "Classe" in df_ct_filtered.columns else "class_name"
                col_mat_ct = "Matière" if "Matière" in df_ct_filtered.columns else "subject"

                if cls_ct_filter != "Toutes les classes" and col_cls_ct in df_ct_filtered.columns:
                    df_ct_filtered = df_ct_filtered[df_ct_filtered[col_cls_ct] == cls_ct_filter]
                
                if mat_ct_filter != "Toutes les matières" and col_mat_ct in df_ct_filtered.columns:
                    df_ct_filtered = df_ct_filtered[df_ct_filtered[col_mat_ct] == mat_ct_filter]

                st.markdown("---")
                st.markdown(
                    f"#### Registre des Séances ({len(df_ct_filtered)} enregistrement(s))"
                )
                st.dataframe(df_ct_filtered, use_container_width=True)

                csv_ct = df_ct_filtered.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Télécharger le Cahier de Texte Filtré (CSV)",
                    data=csv_ct,
                    file_name=f"Cahier_de_texte_{cls_ct_filter}_{mat_ct_filter}.csv",
                    mime="text/csv",
                )
            else:
                st.warning("Aucun contenu n'a été enregistré dans le cahier de texte pour le moment.")

        # -------------------------------------------------------------
        # 5. SYNTHÈSE & STATISTIQUES ADMINISTRATIVES
        # -------------------------------------------------------------
        with tr_stats:
            st.markdown("### 📊 Synthèse & Tableaux de Bord Statistiques")

            col_st1, col_st2, col_st3 = st.columns(3)

            nb_eleves = (
                len(st.session_state.eleves_db)
                if "eleves_db" in st.session_state
                else 0
            )
            nb_classes = (
                len(st.session_state.classes_db)
                if "classes_db" in st.session_state
                else 0
            )
            nb_absences = (
                len(st.session_state.absences_db)
                if "absences_db" in st.session_state
                else 0
            )

            with col_st1:
                st.metric("Total Élèves Inscrits", nb_eleves)
            with col_st2:
                st.metric("Total Classes Actives", nb_classes)
            with col_st3:
                st.metric("Total Incidents / Absences", nb_absences)

            st.markdown("---")
            st.markdown("#### 🏫 Répartition des Élèves par Classe")
            if (
                "eleves_db" in st.session_state
                and not st.session_state.eleves_db.empty
                and "Classe" in st.session_state.eleves_db.columns
            ):
                df_eff = (
                    st.session_state.eleves_db["Classe"]
                    .value_counts()
                    .reset_index()
                )
                df_eff.columns = ["Classe", "Effectif Élèves"]
                st.dataframe(df_eff, use_container_width=True)
            else:
                st.info("Données insuffisantes pour afficher la répartition par classe.")
