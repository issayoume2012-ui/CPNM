# --- BIBLIOTHÈQUES STANDARDS & SUPABASE (Python) ---
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
# 0. CONFIGURATION DE LA PAGE & SUPABASE
# ==========================================
st.set_page_config(
    page_title="Sénégal - Portail Éducatif National École Président Nelson Mandela",
    page_icon="🇸🇳",
    layout="wide",
    initial_sidebar_state="collapsed",
)

SUPABASE_URL = "https://gxzprzTufqvblwoyqihd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd4enByenR1ZnF2Ymx3b3lxaWhkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2NTAwNDgsImV4cCI6MjEwMjIyNjA0OH0.CK9c_hb3bp6q0V7zHBWoX15BwqNHCUSYY9DRXqgOP_Q"

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_supabase()

# ==========================================
# 0. BIS. INITIALISATION SÉCURISÉE DU SESSION_STATE
# ==========================================
if "espace_actif" not in st.session_state:
    st.session_state.espace_actif = "Rapport Global"

if "authenticated_admin" not in st.session_state:
    st.session_state.authenticated_admin = False

def sync_to_supabase(table_name, df):
    """Synchronise un DataFrame avec une table Supabase."""
    try:
        data = df.to_dict(orient="records")
        supabase.table(table_name).upsert(data).execute()
        return True
    except Exception as e:
        st.error(f"Erreur de synchronisation avec Supabase ({table_name}) : {e}")
        return False

def sync_dataframe_to_supabase(table_name, df):
    """Alias fonctionnel robuste pour la synchronisation des DataFrames modifiés via interface."""
    return sync_to_supabase(table_name, df)

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
    if not isinstance(texte, str):
        texte = str(texte) if texte is not None else ""
    return (
        texte.replace("€", "EUR")
        .replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("–", "-")
        .replace("—", "-")
    )

ADMIN_EMAIL = "cpnm@gmail.com"

def enregistrer_log_action(acteur: str, action: str, details: str):
    """Consigne chaque action utilisateur de manière persistante dans Supabase."""
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        supabase.table("journaux_audit").insert({
            "horodatage": horodatage,
            "acteur": acteur,
            "action": action,
            "details": details
        }).execute()
    except Exception as e:
        if "audit_logs_db" not in st.session_state:
            st.session_state.audit_logs_db = pd.DataFrame(columns=["horodatage", "acteur", "action", "details"])
        new_log = pd.DataFrame([{"horodatage": horodatage, "acteur": acteur, "action": action, "details": details}])
        st.session_state.audit_logs_db = pd.concat([st.session_state.audit_logs_db, new_log], ignore_index=True)

def trier_eleves_par_nom(df):
    if df is None or df.empty: return df
    df_copy = df.copy()
    if "Nom" in df_copy.columns and "Prénom" in df_copy.columns:
        df_copy["Nom_Sort"] = df_copy["Nom"].astype(str).str.strip().str.upper()
        df_copy["Prenom_Sort"] = df_copy["Prénom"].astype(str).str.strip().str.upper()
        df_copy = df_copy.sort_values(by=["Nom_Sort", "Prenom_Sort"]).drop(columns=["Nom_Sort", "Prenom_Sort"])
    return df_copy.reset_index(drop=True)

def synchroniser_listes_blanches():
    """Maintient la cohérence absolue et bidirectionnelle des accès professeurs depuis Supabase."""
    try:
        response = supabase.table("enseignants").select("*").execute()
        if response.data:
            st.session_state.prof_credentials = pd.DataFrame(response.data)
            st.session_state.prof_white_list = st.session_state.prof_credentials.copy()
    except Exception:
        pass


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
# 1. DESIGN XXL & STYLISME CSS
# ==========================================
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
# 2. INITIALISATION EXHAUSTIVE ET SYNCHRONISATION SUPABASE
# ==========================================
if "espace_actif" not in st.session_state:
    st.session_state.espace_actif = "Rapport Global"

if "authenticated_admin" not in st.session_state:
    st.session_state.authenticated_admin = False

if "edt_documents" not in st.session_state:
    st.session_state.edt_documents = {}

# --- CHARGEMENT / INITIALISATION DES ADMINISTRATEURS ---
try:
    res_admin = supabase.table("administrateurs").select("*").execute()
    if res_admin.data and len(res_admin.data) > 0:
        st.session_state.admin_credentials = pd.DataFrame(res_admin.data)
    else:
        st.session_state.admin_credentials = pd.DataFrame([{
            "Nom": "Principal",
            "Prénom": "Admin",
            "Email": ADMIN_EMAIL,
            "Mot de passe": hacher_mot_de_passe("cpnm2026"),
            "Niveau d'accès": "Super-Admin Ayant-Droit",
        }])
except Exception:
    if "admin_credentials" not in st.session_state:
        st.session_state.admin_credentials = pd.DataFrame([{
            "Nom": "Principal",
            "Prénom": "Admin",
            "Email": ADMIN_EMAIL,
            "Mot de passe": hacher_mot_de_passe("cpnm2026"),
            "Niveau d'accès": "Super-Admin Ayant-Droit",
        }])

if "admin_white_list" not in st.session_state:
    st.session_state.admin_white_list = st.session_state.admin_credentials.copy()

# --- CHARGEMENT / INITIALISATION DES PROFESSEURS ---
if "prof_credentials" not in st.session_state:
    try:
        res_prof = supabase.table("enseignants").select("*").execute()
        if res_prof.data:
            st.session_state.prof_credentials = pd.DataFrame(res_prof.data)
        else:
            st.session_state.prof_credentials = pd.DataFrame(columns=["Nom", "Prénom", "Email", "Matière Principale", "Classe Attribuée", "Mot de passe"])
    except Exception:
        st.session_state.prof_credentials = pd.DataFrame(columns=["Nom", "Prénom", "Email", "Matière Principale", "Classe Attribuée", "Mot de passe"])

for col in ["Nom", "Prénom", "Email", "Matière Principale", "Classe Attribuée", "Mot de passe"]:
    if col not in st.session_state.prof_credentials.columns:
        st.session_state.prof_credentials[col] = ""

if "prof_white_list" not in st.session_state:
    st.session_state.prof_white_list = st.session_state.prof_credentials.copy()

# --- CHARGEMENT / INITIALISATION DES PARENTS ---
if "parents_white_list" not in st.session_state:
    try:
        res_parents = supabase.table("parents").select("*").execute()
        if res_parents.data:
            st.session_state.parents_white_list = pd.DataFrame(res_parents.data)
        else:
            st.session_state.parents_white_list = pd.DataFrame(columns=["Téléphone", "Prénom Élève", "Nom Élève", "Année Naissance", "Classe"])
    except Exception:
        st.session_state.parents_white_list = pd.DataFrame(columns=["Téléphone", "Prénom Élève", "Nom Élève", "Année Naissance", "Classe"])

# --- CHARGEMENT / INITIALISATION DES CLASSES ---
if "classes_db" not in st.session_state:
    try:
        res_classes = supabase.table("classes").select("*").execute()
        if res_classes.data:
            st.session_state.classes_db = pd.DataFrame(res_classes.data)
        else:
            st.session_state.classes_db = pd.DataFrame(
                columns=["Classe", "Cycle", "Professeur Responsable"],
                data=[
                    ["6ème A", "Collège", "Prof. Math"],
                    ["CP", "Élémentaire", "Prof. Élémen"]
                ],
            )
    except Exception:
        st.session_state.classes_db = pd.DataFrame(
            columns=["Classe", "Cycle", "Professeur Responsable"],
            data=[
                ["6ème A", "Collège", "Prof. Math"],
                ["CP", "Élémentaire", "Prof. Élémen"]
            ],
        )

# --- CHARGEMENT / INITIALISATION DES ÉLÈVES ---
if "eleves_db" not in st.session_state:
    try:
        res_eleves = supabase.table("eleves").select("*").execute()
        if res_eleves.data:
            st.session_state.eleves_db = pd.DataFrame(res_eleves.data)
        else:
            st.session_state.eleves_db = pd.DataFrame(columns=["Nom Complet", "Prénom", "Nom", "Date de Naissance", "Classe", "Photo"], data=[])
    except Exception:
        st.session_state.eleves_db = pd.DataFrame(columns=["Nom Complet", "Prénom", "Nom", "Date de Naissance", "Classe", "Photo"], data=[])

for col_req in ["Nom Complet", "Prénom", "Nom", "Date de Naissance", "Classe", "Photo"]:
    if col_req not in st.session_state.eleves_db.columns:
        st.session_state.eleves_db[col_req] = ""

if not st.session_state.eleves_db.empty:
    st.session_state.eleves_db = trier_eleves_par_nom(st.session_state.eleves_db)

# --- CHARGEMENT / INITIALISATION DES MATIÈRES ---
if "matieres_def" not in st.session_state:
    try:
        res_mat = supabase.table("matieres").select("*").execute()
        if res_mat.data:
            st.session_state.matieres_def = pd.DataFrame(res_mat.data)
        else:
            st.session_state.matieres_def = pd.DataFrame([
                {"Matière": "Mathématiques", "Cycle": "Collège", "Coefficient": 4, "Barème": 20},
                {"Matière": "Français", "Cycle": "Collège", "Coefficient": 5, "Barème": 20},
                {"Matière": "Histoire-Géographie", "Cycle": "Collège", "Coefficient": 2, "Barème": 20},
                {"Matière": "SVT", "Cycle": "Collège", "Coefficient": 2, "Barème": 20},
                {"Matière": "Anglais", "Cycle": "Collège", "Coefficient": 2, "Barème": 20},
                {"Matière": "Physique-Chimie", "Cycle": "Collège", "Coefficient": 2, "Barème": 20},
                {"Matière": "Lecture / Langage", "Cycle": "Élémentaire", "Coefficient": 1, "Barème": 50},
                {"Matière": "Calcul / Mathématiques", "Cycle": "Élémentaire", "Coefficient": 1, "Barème": 50},
                {"Matière": "Éveil / Science", "Cycle": "Élémentaire", "Coefficient": 1, "Barème": 30},
                {"Matière": "Éducation Civique", "Cycle": "Élémentaire", "Coefficient": 1, "Barème": 20},
            ])
    except Exception:
        st.session_state.matieres_def = pd.DataFrame([
            {"Matière": "Mathématiques", "Cycle": "Collège", "Coefficient": 4, "Barème": 20},
            {"Matière": "Français", "Cycle": "Collège", "Coefficient": 5, "Barème": 20},
            {"Matière": "Histoire-Géographie", "Cycle": "Collège", "Coefficient": 2, "Barème": 20},
            {"Matière": "SVT", "Cycle": "Collège", "Coefficient": 2, "Barème": 20},
            {"Matière": "Anglais", "Cycle": "Collège", "Coefficient": 2, "Barème": 20},
            {"Matière": "Physique-Chimie", "Cycle": "Collège", "Coefficient": 2, "Barème": 20},
            {"Matière": "Lecture / Langage", "Cycle": "Élémentaire", "Coefficient": 1, "Barème": 50},
            {"Matière": "Calcul / Mathématiques", "Cycle": "Élémentaire", "Coefficient": 1, "Barème": 50},
            {"Matière": "Éveil / Science", "Cycle": "Élémentaire", "Coefficient": 1, "Barème": 30},
            {"Matière": "Éducation Civique", "Cycle": "Élémentaire", "Coefficient": 1, "Barème": 20},
        ])

if "Barème" not in st.session_state.matieres_def.columns:
    st.session_state.matieres_def["Barème"] = (
        st.session_state.matieres_def["Cycle"].apply(lambda x: 20 if x == "Collège" else 50)
    )

if "coefficients_db" not in st.session_state:
    try:
        res_coef = supabase.table("coefficients").select("*").execute()
        if res_coef.data:
            st.session_state.coefficients_db = pd.DataFrame(res_coef.data)
        else:
            st.session_state.coefficients_db = pd.DataFrame([
                {"Classe": "6ème A", "Matière": "Mathématiques", "Coefficient": 4, "Barème": 20},
                {"Classe": "6ème A", "Matière": "Français", "Coefficient": 5, "Barème": 20},
                {"Classe": "6ème A", "Matière": "Histoire-Géographie", "Coefficient": 2, "Barème": 20},
                {"Classe": "6ème A", "Matière": "SVT", "Coefficient": 2, "Barème": 20},
                {"Classe": "6ème A", "Matière": "Anglais", "Coefficient": 2, "Barème": 20},
                {"Classe": "6ème A", "Matière": "Physique-Chimie", "Coefficient": 2, "Barème": 20},
                {"Classe": "CP", "Matière": "Lecture / Langage", "Coefficient": 1, "Barème": 50},
                {"Classe": "CP", "Matière": "Calcul / Mathématiques", "Coefficient": 1, "Barème": 50},
                {"Classe": "CP", "Matière": "Éveil / Science", "Coefficient": 1, "Barème": 30},
                {"Classe": "CP", "Matière": "Éducation Civique", "Coefficient": 1, "Barème": 20},
            ])
    except Exception:
        st.session_state.coefficients_db = pd.DataFrame([
            {"Classe": "6ème A", "Matière": "Mathématiques", "Coefficient": 4, "Barème": 20},
            {"Classe": "6ème A", "Matière": "Français", "Coefficient": 5, "Barème": 20},
            {"Classe": "6ème A", "Matière": "Histoire-Géographie", "Coefficient": 2, "Barème": 20},
            {"Classe": "6ème A", "Matière": "SVT", "Coefficient": 2, "Barème": 20},
            {"Classe": "6ème A", "Matière": "Anglais", "Coefficient": 2, "Barème": 20},
            {"Classe": "6ème A", "Matière": "Physique-Chimie", "Coefficient": 2, "Barème": 20},
            {"Classe": "CP", "Matière": "Lecture / Langage", "Coefficient": 1, "Barème": 50},
            {"Classe": "CP", "Matière": "Calcul / Mathématiques", "Coefficient": 1, "Barème": 50},
            {"Classe": "CP", "Matière": "Éveil / Science", "Coefficient": 1, "Barème": 30},
            {"Classe": "CP", "Matière": "Éducation Civique", "Coefficient": 1, "Barème": 20},
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

# --- CHARGEMENT DES NOTES ---
if "notes_db" not in st.session_state:
    try:
        res_notes = supabase.table("notes").select("*").execute()
        if res_notes.data:
            st.session_state.notes_db = pd.DataFrame(res_notes.data)
        else:
            st.session_state.notes_db = pd.DataFrame(columns=["Classe", "Matière", "Periode", "Période", "Eleve", "Devoir1", "Devoir2", "Composition", "BaremeNote"], data=[])
    except Exception:
        st.session_state.notes_db = pd.DataFrame(columns=["Classe", "Matière", "Periode", "Période", "Eleve", "Devoir1", "Devoir2", "Composition", "BaremeNote"], data=[])

if isinstance(st.session_state.notes_db, pd.DataFrame):
    st.session_state.notes_db = st.session_state.notes_db.reset_index(drop=True)
    if "BaremeNote" not in st.session_state.notes_db.columns:
        st.session_state.notes_db["BaremeNote"] = 20.0

if "Periode" not in st.session_state.notes_db.columns and "Période" in st.session_state.notes_db.columns:
    st.session_state.notes_db["Periode"] = st.session_state.notes_db["Période"]
elif "Période" not in st.session_state.notes_db.columns and "Periode" in st.session_state.notes_db.columns:
    st.session_state.notes_db["Période"] = st.session_state.notes_db["Periode"]
elif "Periode" not in st.session_state.notes_db.columns and "Période" not in st.session_state.notes_db.columns:
    st.session_state.notes_db["Periode"] = "1er Semestre"
    st.session_state.notes_db["Période"] = "1er Semestre"

# --- CHARGEMENT DE LA VIE SCOLAIRE ---
if "viescolaire_db" not in st.session_state:
    try:
        res_vs = supabase.table("viescolaire").select("*").execute()
        if res_vs.data:
            st.session_state.viescolaire_db = pd.DataFrame(res_vs.data)
        else:
            st.session_state.viescolaire_db = pd.DataFrame(columns=["Classe", "Periode", "Période", "Eleve", "AbsencesJustifiees", "AbsencesNonJustifiees", "Retards", "HeuresPerdues", "Observations", "DecisionConseil"], data=[])
    except Exception:
        st.session_state.viescolaire_db = pd.DataFrame(columns=["Classe", "Periode", "Période", "Eleve", "AbsencesJustifiees", "AbsencesNonJustifiees", "Retards", "HeuresPerdues", "Observations", "DecisionConseil"], data=[])

# --- CHARGEMENT DU TRAVAIL À FAIRE ---
if "travail_a_faire_db" not in st.session_state:
    try:
        res_taf = supabase.table("travail_a_faire").select("*").execute()
        if res_taf.data:
            st.session_state.travail_a_faire_db = pd.DataFrame(res_taf.data)
        else:
            st.session_state.travail_a_faire_db = pd.DataFrame(columns=["ID", "Professeur", "DatePublication", "DateRendu", "Classe", "Matière", "Titre", "Consignes", "LienUrl", "LienVideo", "FichierNom", "FichierB64", "FichierType"], data=[])
    except Exception:
        st.session_state.travail_a_faire_db = pd.DataFrame(columns=["ID", "Professeur", "DatePublication", "DateRendu", "Classe", "Matière", "Titre", "Consignes", "LienUrl", "LienVideo", "FichierNom", "FichierB64", "FichierType"], data=[])

# --- CHARGEMENT DES MESSAGES PARENTS ---
if "messages_parents_db" not in st.session_state:
    try:
        res_msg = supabase.table("messages_parents").select("*").execute()
        if res_msg.data:
            st.session_state.messages_parents_db = pd.DataFrame(res_msg.data)
        else:
            st.session_state.messages_parents_db = pd.DataFrame(columns=["ID", "Emetteur", "RoleEmetteur", "DateEnvoi", "Classe", "Objet", "Message", "Urgent"], data=[])
    except Exception:
        st.session_state.messages_parents_db = pd.DataFrame(columns=["ID", "Emetteur", "RoleEmetteur", "DateEnvoi", "Classe", "Objet", "Message", "Urgent"], data=[])

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
    try:
        res_ct = supabase.table("cahier_textes").select("*").execute()
        if res_ct.data:
            st.session_state.cahier_textes = pd.DataFrame(res_ct.data)
        else:
            st.session_state.cahier_textes = pd.DataFrame(columns=["Professeur", "Date", "Classe", "Matière", "Contenu", "Travail à faire"], data=[])
    except Exception:
        st.session_state.cahier_textes = pd.DataFrame(columns=["Professeur", "Date", "Classe", "Matière", "Contenu", "Travail à faire"], data=[])

if "absences_db" not in st.session_state:
    try:
        res_abs = supabase.table("absences").select("*").execute()
        if res_abs.data:
            st.session_state.absences_db = pd.DataFrame(res_abs.data)
        else:
            st.session_state.absences_db = pd.DataFrame(columns=["Date", "Classe", "Élève", "Statut", "Motif"], data=[])
    except Exception:
        st.session_state.absences_db = pd.DataFrame(columns=["Date", "Classe", "Élève", "Statut", "Motif"], data=[])

synchroniser_listes_blanches()

# ==========================================
# 3. FONCTIONS MÉTIER & UTILITAIRES DE CALCUL
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
            "6ÈME", "6EME", "5ÈME", "5EME", "4ÈME", "4EME", "3ÈME", "3EME", "COLLÈGE", "COLLEGE"
        ]
    ):
        return "Collège"
    if any(
        classe_clean.startswith(prefix)
        for prefix in ["CI", "CP", "CE1", "CE2", "CM1", "CM2", "ÉLÉMENTAIRE", "ELEMENTAIRE"]
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
        font_family = "DejaVu" if "DejaVu" in pdf.core_fonts or hasattr(pdf, "fonts") and "DejaVu" in pdf.fonts else "Arial"
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
    pdf.cell(0, 4, nettoyer_texte_pdf("INSPECTION D'ACADÉMIE DE SAINT-LOUIS (IA SAINT-LOUIS)"), 0, 1, "C")
    pdf.set_font(font_family, "B", 9)
    pdf.cell(0, 4, nettoyer_texte_pdf("INSPECTION DE L'ÉDUCATION ET DE LA FORMATION DE SAINT-LOUIS (IEF SAINT-LOUIS)"), 0, 1, "C")
    pdf.set_font(font_family, "B", 10)
    pdf.cell(0, 5, nettoyer_texte_pdf("ÉCOLE PRÉSIDENT NELSON MANDELA"), 0, 1, "C")

    if titre_document:
        pdf.set_font(font_family, "B", 11)
        pdf.set_text_color(14, 165, 233)
        pdf.cell(0, 6, nettoyer_texte_pdf(titre_document.upper()), 0, 1, "C")
        pdf.set_text_color(0, 0, 0)

    pdf.set_draw_color(14, 165, 233)
    if hasattr(pdf, "set_line_width"):
        pdf.set_line_width(0.8)
    pdf.line(10, 38, 200, 38)
    pdf.ln(5)

def ajouter_bloc_signatures(pdf, prof_nom="Le Professeur", chef_nom="Le Chef d'Établissement / IEF"):
    try:
        font_family = "DejaVu" if "DejaVu" in pdf.core_fonts or hasattr(pdf, "fonts") and "DejaVu" in pdf.fonts else "Arial"
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
    pdf.cell(90, 15, nettoyer_texte_pdf("Cachet officiel de l'Établissement d'Excellence"), "LRB", 1, "C")

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
                m_def[m_def["Cycle"].apply(est_cycle_elementaire) == is_elem]["Matière"]
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
            cond_per = (notes_df["Periode"] == periode) | (notes_df["Période"] == periode)
        elif "Periode" in notes_df.columns:
            cond_per = notes_df["Periode"] == periode
        elif "Période" in notes_df.columns:
            cond_per = notes_df["Période"] == periode
        else:
            cond_per = True

        m_notes = notes_df[cond_cls & cond_per]["Matière"].dropna().unique().tolist()
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
            if not notes_classe_periode.empty and "Eleve" in notes_classe_periode.columns
            else pd.DataFrame()
        )
        note_mat = (
            note_row[note_row["Matière"] == mat]
            if not note_row.empty and "Matière" in note_row.columns
            else pd.DataFrame()
        )

        d1, d2, comp = 0.0, 0.0, 0.0
        if not note_mat.empty:
            d1_val = note_mat.iloc[0]["Devoir1"] if "Devoir1" in note_mat.columns else 0.0
            d2_val = note_mat.iloc[0]["Devoir2"] if "Devoir2" in note_mat.columns else 0.0
            comp_val = note_mat.iloc[0]["Composition"] if "Composition" in note_mat.columns else 0.0

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
                "Appreciation": obtenir_appreciation(moy_matiere, cycle_classe, bareme_m),
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
            moyenne_generale = round((total_points_global / total_bareme_global) * 10.0, 2)
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
            st.session_state.eleves_db[st.session_state.eleves_db["Classe"] == classe]
        )
        tous_eleves = df_sorted_el["Nom Complet"].tolist()

    moyennes_classe = {}
    for el in tous_eleves:
        pts = 0.0
        coefs = 0.0
        bareme_tot_el = 0.0
        notes_el_p = (
            notes_classe_periode[notes_classe_periode["Eleve"] == el]
            if not notes_classe_periode.empty and "Eleve" in notes_classe_periode.columns
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
                d1_val = n_m.iloc[0]["Devoir1"] if "Devoir1" in n_m.columns else 0.0
                d2_val = n_m.iloc[0]["Devoir2"] if "Devoir2" in n_m.columns else 0.0
                comp_val = n_m.iloc[0]["Composition"] if "Composition" in n_m.columns else 0.0
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
            moyennes_classe[el] = round(pts / coefs, 2) if coefs > 0 else 0.0

    classement_trie = sorted(moyennes_classe.items(), key=lambda x: x[1], reverse=True)
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
        0, 0, 0, 0, "RAS", "Encouragements"
    )
    if not vs_row.empty:
        abs_just = int(vs_row.iloc[0]["AbsencesJustifiees"]) if "AbsencesJustifiees" in vs_row.columns and pd.notna(vs_row.iloc[0]["AbsencesJustifiees"]) else 0
        abs_non_just = int(vs_row.iloc[0]["AbsencesNonJustifiees"]) if "AbsencesNonJustifiees" in vs_row.columns and pd.notna(vs_row.iloc[0]["AbsencesNonJustifiees"]) else 0
        retards = int(vs_row.iloc[0]["Retards"]) if "Retards" in vs_row.columns and pd.notna(vs_row.iloc[0]["Retards"]) else 0
        heures_p = int(vs_row.iloc[0]["HeuresPerdues"]) if "HeuresPerdues" in vs_row.columns and pd.notna(vs_row.iloc[0]["HeuresPerdues"]) else 0
        obs = str(vs_row.iloc[0]["Observations"]) if "Observations" in vs_row.columns and pd.notna(vs_row.iloc[0]["Observations"]) else "RAS"
        decision = str(vs_row.iloc[0]["DecisionConseil"]) if "DecisionConseil" in vs_row.columns and pd.notna(vs_row.iloc[0]["DecisionConseil"]) else "Encouragements"

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

# ==========================================
# 4. MODULE DE GÉNÉRATION DES DOCUMENTS PDF
# ==========================================
def generer_pdf_bulletin(bul_data):
    pdf = FPDF()
    try:
        font_family = "DejaVu" if os.path.exists("DejaVuSans.ttf") else "Arial"
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
        headers = ["Matière", "Coef", "Dev 1", "Dev 2", "Comp", "Moy/20", "Appréciation"]

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
            0, 6,
            nettoyer_texte_pdf(
                f"Moyenne Générale : {bul_data['moyenne_generale']} / {bul_data['total_bareme']} | Total Points : {bul_data['total_points']}"
            ),
            1, 1, "L", True,
        )
    else:
        pdf.cell(
            0, 6,
            nettoyer_texte_pdf(
                f"Moyenne Générale : {bul_data['moyenne_generale']} / 20 | Total Points : {bul_data['total_points']}"
            ),
            1, 1, "L", True,
        )
    pdf.ln(3)

    pdf.set_font(font_family, "B", 9)
    pdf.cell(0, 5, nettoyer_texte_pdf("BILAN DE LA VIE SCOLAIRE ET DISCIPLINE"), 0, 1, "L")
    pdf.set_font(font_family, "", 9)
    pdf.cell(
        0, 5,
        nettoyer_texte_pdf(
            f"Absences justifiées : {bul_data['abs_just']} | Absences non justifiées : {bul_data['abs_non_just']} | Retards : {bul_data['retards']} | Heures perdues : {bul_data['heures_perdues']}h"
        ),
        1, 1, "L",
    )
    pdf.cell(
        0, 5,
        nettoyer_texte_pdf(f"Observations / Appréciation générale : {bul_data['observations']}"),
        1, 1, "L",
    )
    pdf.cell(
        0, 5,
        nettoyer_texte_pdf(f"Décision du Conseil de Classe : {bul_data['decision']}"),
        1, 1, "L",
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
            filename = f"Bulletin_{classe}_{eleve.replace(' ', '_')}_{periode.replace(' ', '_')}.pdf"
            zip_file.writestr(filename, pdf_bytes)
    return zip_buffer.getvalue()

def generer_pdf_liste_eleves_classe(classe):
    if "eleves_db" not in st.session_state or st.session_state.eleves_db.empty:
        df_eleves = pd.DataFrame(columns=["Nom Complet", "Classe", "Date de Naissance"])
    else:
        if "Classe" in st.session_state.eleves_db.columns:
            df_eleves = st.session_state.eleves_db[st.session_state.eleves_db["Classe"] == classe]
        else:
            df_eleves = pd.DataFrame(columns=["Nom Complet", "Classe", "Date de Naissance"])

    df_eleves = trier_eleves_par_nom(df_eleves)
    pdf = FPDF()
    try:
        font_family = "DejaVu" if os.path.exists("DejaVuSans.ttf") else "Arial"
    except Exception:
        font_family = "Arial"

    pdf.add_page()
    ajouter_entete_senegal_officiel(pdf, f"FICHE OFFICIELLE DE LA CLASSE : {classe} (Tri Alphabétique Nom)")

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
            pdf.cell(col_widths[0], 6, nettoyer_texte_pdf(str(row.get("Nom Complet", ""))[:35]), 1, 0, "L", fill)
            pdf.cell(col_widths[1], 6, nettoyer_texte_pdf(str(row.get("Classe", ""))[:20]), 1, 0, "C", fill)
            pdf.cell(col_widths[2], 6, nettoyer_texte_pdf(str(row.get("Date de Naissance", ""))[:20]), 1, 0, "C", fill)
            pdf.ln()
            fill = not fill
    else:
        pdf.cell(190, 6, nettoyer_texte_pdf("Aucun élève répertorié dans cette classe."), 1, 1, "C")

    ajouter_bloc_signatures(pdf, prof_nom="Responsable de Scolarité", chef_nom="Inspecteur IEF Saint-Louis")
    
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
    df_abs = st.session_state.absences_db if "absences_db" in st.session_state else pd.DataFrame()
    if not df_abs.empty and classe_filtre != "Toutes" and "Classe" in df_abs.columns:
        df_abs = df_abs[df_abs["Classe"] == classe_filtre]

    pdf = FPDF()
    try:
        font_family = "DejaVu" if os.path.exists("DejaVuSans.ttf") else "Arial"
    except Exception:
        font_family = "Arial"

    pdf.add_page()
    ajouter_entete_senegal_officiel(pdf, f"REGISTRE OFFICIEL DES ABSENCES & RETARDS - {classe_filtre.upper()}")

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

    ajouter_bloc_signatures(pdf, prof_nom="Surveillant Général", chef_nom="Chef d'Établissement")
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
# 5. EN-TÊTE INSTITUTIONNEL & NAVIGATION GLOBALE (RAPPORT GLOBAL)
# ==========================================
logo_element_html = '<div class="emblem-box"><span style="font-size: 3.2rem;">🇸🇳</span></div>'

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

if st.session_state.espace_actif != "Rapport Global":
    col_ret1, col_ret2 = st.columns([1, 5])
    with col_ret1:
        if st.button("⬅️ Retour Rapport Global"):
            st.session_state.espace_actif = "Rapport Global"
            st.rerun()
    st.markdown("---")

# ==========================================
# 6. ROUTAGE DES ESPACES SECONDAIRES & SUPABASE (RAPPORT GLOBAL / ACCUEIL)
# ==========================================
if st.session_state.espace_actif == "Rapport Global":
    st.markdown("""
        <div style="text-align: center; padding: 15px 0 35px 0;">
            <h1 style="color: #0F172A; font-weight: 900; font-size: 2.8rem;">Éduquer • Instruire • Promouvoir les Vertus Africaines</h1>
            <p style="font-size: 1.25rem; color: #334155; max-width: 1000px; margin: 0 auto; font-weight: 500;">
                Bâtir l'élite de demain sous la tutelle de l'IA Saint-Louis et l'IEF Saint-Louis. Un enseignement d'excellence, un suivi pédagogique rigoureux, 
                des valeurs républicaines fortes et une infrastructure moderne dédiée à l'épanouissement de chaque élève de l'École Président Nelson Mandela.
            </p>
        </div>
        """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown("""
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">👨‍🏫</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0; font-weight: 800;">Espace Professeurs</h3>
                <p style="font-size: 0.95rem; color: #475569; font-weight: 600;">Encadrement d'excellence : saisie rigoureuse des notes, suivi des présences, cahier de texte et assignation des travaux à faire.</p>
            </div>
            """, unsafe_allow_html=True)
        if st.button("Accéder Professeur", key="btn_p"):
            st.session_state.espace_actif = "👨‍🏫 Espace Professeurs / Maîtres"
            st.rerun()

    with c2:
        st.markdown("""
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">👨‍👩‍👧</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0; font-weight: 800;">Espace Parents</h3>
                <p style="font-size: 0.95rem; color: #475569; font-weight: 600;">Partenariat école-famille : suivi des travaux à faire, consultation des emplois du temps, vie scolaire et annonces officielles.</p>
            </div>
            """, unsafe_allow_html=True)
        if st.button("Accéder Parent", key="btn_pa"):
            st.session_state.espace_actif = "👨‍👩‍👧 Espace Parents / Élèves"
            st.rerun()

    with c3:
        st.markdown("""
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">🔒</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0; font-weight: 800;">Administration</h3>
                <p style="font-size: 0.95rem; color: #475569; font-weight: 600;">Pilotage stratégique de l'établissement et gestion rigoureuse des habilitations pour une sécurité optimale.</p>
            </div>
            """, unsafe_allow_html=True)
        if st.button("Accéder Admin", key="btn_ad"):
            st.session_state.espace_actif = "🔒 Espace Administration (Sécurisé)"
            st.rerun()

    with c4:
        st.markdown("""
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">🏫</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0; font-weight: 800;">Administration XXL & Rapports</h3>
                <p style="font-size: 0.95rem; color: #475569; font-weight: 600;">Tableaux de bord d'excellence, téléchargement des bulletins PDF officiels et assistant pédagogique intelligent.</p>
            </div>
            """, unsafe_allow_html=True)
        if st.button("Accéder Rapports", key="btn_rp"):
            st.session_state.espace_actif = "🏫 Administration XXL & Rapports"
            st.rerun()

elif st.session_state.espace_actif == "🏫 Administration XXL & Rapports":
    st.markdown(
        '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Rapports Globaux, Téléchargements & Pilotage Administratif</div>',
        unsafe_allow_html=True,
    )

    if not st.session_state.get("authenticated_admin", False):
        st.error("🔒 Accès restreint : Vous devez être connecté en tant qu'Administrateur pour accéder à cet espace.")
        st.info("Veuillez vous rendre dans l'onglet **🔒 Espace Administration (Sécurisé)** pour vous authentifier.")
    else:
        tr_bulletins, tr_listes, tr_absences, tr_cahier, tr_stats = st.tabs([
            "📄 Édition & Téléchargement des Bulletins",
            "📋 Fiches Officielles de Classe (Tri Nom)",
            "📉 Registre des Absences",
            "📑 Registre Général des Cahiers de Texte",
            "📊 Synthèse & Tableaux de Bord Statistiques",
        ])

        with tr_bulletins:
            st.markdown("### 📄 Génération & Téléchargement des Bulletins par Élève")
            if "classes_db" in st.session_state and not st.session_state.classes_db.empty:
                cls_rep = st.selectbox("Sélectionner la classe", st.session_state.classes_db["Classe"].unique(), key="rep_cls_sel")
                pers_rep = obtenir_periodes_pour_classe(cls_rep)

                if pers_rep:
                    per_rep = st.selectbox("Sélectionner la période", pers_rep, key="rep_per_sel")
                    df_el_rep = pd.DataFrame()
                    if "eleves_db" in st.session_state and "Classe" in st.session_state.eleves_db.columns:
                        df_el_rep = trier_eleves_par_nom(
                            st.session_state.eleves_db[st.session_state.eleves_db["Classe"] == cls_rep]
                        )

                    if not df_el_rep.empty:
                        list_el_rep = df_el_rep["Nom Complet"].tolist()
                        el_rep_sel = st.selectbox("Sélectionner un élève spécifique", list_el_rep, key="rep_el_sel")

                        bul_data_individual = calculer_bulletin_eleve(cls_rep, el_rep_sel, per_rep)

                        st.markdown(f"#### Bulletin de : **{el_rep_sel}** ({cls_rep} - {per_rep})")
                        st.dataframe(pd.DataFrame(bul_data_individual["lignes"]), use_container_width=True)

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
                        st.warning("Aucun élève dans cette classe.")

        with tr_listes:
            st.markdown("### 📋 Imprimer les Fiches de Classe (Tri Alphabétique Nom)")
            if "classes_db" in st.session_state and not st.session_state.classes_db.empty:
                cls_fiche = st.selectbox("Sélectionner la classe pour la fiche", st.session_state.classes_db["Classe"].unique(), key="fiche_cls_sel")
                pdf_fiche_bytes = generer_pdf_liste_eleves_classe(cls_fiche)
                st.download_button(
                    f"📥 Télécharger la Liste Officielle de {cls_fiche} (PDF)",
                    data=pdf_fiche_bytes,
                    file_name=f"Liste_Eleves_{cls_fiche}.pdf",
                    mime="application/pdf",
                )

        with tr_absences:
            st.markdown("### 📉 Registre des Absences et Retards & Téléchargement PDF")
            cls_abs_sel = st.selectbox(
                "Filtrer par classe",
                ["Toutes"] + list(st.session_state.classes_db["Classe"].unique()) if "classes_db" in st.session_state else ["Toutes"],
                key="abs_report_cls_sel",
            )

            df_abs_disp = st.session_state.absences_db if "absences_db" in st.session_state else pd.DataFrame()
            if not df_abs_disp.empty and cls_abs_sel != "Toutes" and "Classe" in df_abs_disp.columns:
                df_abs_disp = df_abs_disp[df_abs_disp["Classe"] == cls_abs_sel]

            if not df_abs_disp.empty:
                edited_absences = st.data_editor(
                    df_abs_disp,
                    use_container_width=True,
                    key="editor_absences_supabase",
                    num_rows="dynamic"
                )
                
                if st.button("🔄 Synchroniser les modifications des absences avec Supabase", key="btn_sync_abs"):
                    try:
                        success = sync_dataframe_to_supabase("absences", edited_absences)
                        if success:
                            st.session_state.absences_db = edited_absences
                            enregistrer_log_action("Admin", "Synchronisation", "Mise à jour du registre des absences")
                            st.success("✅ Registre des absences synchronisé avec succès dans Supabase !")
                        else:
                            st.error("❌ Erreur lors de la synchronisation avec Supabase.")
                    except Exception as e:
                        st.error(f"❌ Une exception s'est produite : {e}")

                pdf_abs_bytes = generer_pdf_liste_absences(cls_abs_sel)
                st.download_button(
                    f"📥 Télécharger la Liste des Absences ({cls_abs_sel}) (PDF)",
                    data=pdf_abs_bytes,
                    file_name=f"Registre_Absences_{cls_abs_sel}.pdf",
                    mime="application/pdf",
                )
            else:
                st.info("Aucune absence ou retard répertorié pour cette sélection.")

        with tr_cahier:
            st.markdown("### 📑 Consultation des Cahiers de Texte Enseignants")
            df_ct_all = st.session_state.cahier_textes if "cahier_textes" in st.session_state else pd.DataFrame()

            if not df_ct_all.empty:
                col_f_ct1, col_f_ct2 = st.columns(2)
                with col_f_ct1:
                    cls_options = ["Toutes les classes"]
                    if "classes_db" in st.session_state and not st.session_state.classes_db.empty:
                        cls_options += list(st.session_state.classes_db["Classe"].unique())
                    cls_ct_filter = st.selectbox("Filtrer par classe", cls_options, key="admin_filter_ct_cls")
                with col_f_ct2:
                    mat_options = ["Toutes les matières"]
                    if "Matière" in df_ct_all.columns:
                        mat_options += list(df_ct_all["Matière"].dropna().unique())
                    mat_ct_filter = st.selectbox("Filtrer par matière", mat_options, key="admin_filter_ct_mat")

                df_ct_filtered = df_ct_all.copy()
                if cls_ct_filter != "Toutes les classes" and "Classe" in df_ct_filtered.columns:
                    df_ct_filtered = df_ct_filtered[df_ct_filtered["Classe"] == cls_ct_filter]
                if mat_ct_filter != "Toutes les matières" and "Matière" in df_ct_filtered.columns:
                    df_ct_filtered = df_ct_filtered[df_ct_filtered["Matière"] == mat_ct_filter]

                st.markdown("---")
                st.markdown(f"#### Registre des Séances ({len(df_ct_filtered)} enregistrement(s))")
                
                edited_cahier = st.data_editor(
                    df_ct_filtered,
                    use_container_width=True,
                    key="editor_cahier_supabase",
                    num_rows="dynamic"
                )
                
                if st.button("🔄 Synchroniser les modifications du cahier de texte", key="btn_sync_cahier"):
                    try:
                        success = sync_dataframe_to_supabase("cahier_textes", edited_cahier)
                        if success:
                            st.session_state.cahier_textes = edited_cahier
                            enregistrer_log_action("Admin", "Synchronisation", "Mise à jour du cahier de textes")
                            st.success("✅ Cahier de textes synchronisé avec succès dans Supabase !")
                        else:
                            st.error("❌ Erreur lors de la synchronisation avec Supabase.")
                    except Exception as e:
                        st.error(f"❌ Une exception s'est produite : {e}")

                csv_ct = df_ct_filtered.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Télécharger le Cahier de Texte Filtré (CSV)",
                    data=csv_ct,
                    file_name=f"Cahier_de_texte_{cls_ct_filter}_{mat_ct_filter}.csv",
                    mime="text/csv",
                )
            else:
                st.warning("Aucun contenu n'a été enregistré dans le cahier de texte pour le moment.")

        with tr_stats:
            st.markdown("### 📊 Synthèse & Tableaux de Bord Statistiques")
            col_st1, col_st2, col_st3 = st.columns(3)

            nb_eleves = len(st.session_state.eleves_db) if "eleves_db" in st.session_state else 0
            nb_classes = len(st.session_state.classes_db) if "classes_db" in st.session_state else 0
            nb_absences = len(st.session_state.absences_db) if "absences_db" in st.session_state else 0

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
                df_eff = st.session_state.eleves_db["Classe"].value_counts().reset_index()
                df_eff.columns = ["Classe", "Effectif Élèves"]
                
                edited_eleves = st.data_editor(
                    st.session_state.eleves_db,
                    use_container_width=True,
                    key="editor_eleves_db_supabase",
                    num_rows="dynamic"
                )
                
                if st.button("🔄 Synchroniser la base élèves et effectifs avec Supabase", key="btn_sync_eleves"):
                    try:
                        success = sync_dataframe_to_supabase("eleves", edited_eleves)
                        if success:
                            st.session_state.eleves_db = edited_eleves
                            enregistrer_log_action("Admin", "Synchronisation", "Mise à jour de la base des élèves")
                            st.success("✅ Base des élèves et répartition synchronisées avec Supabase avec succès !")
                            st.rerun()
                        else:
                            st.error("❌ Échec de la synchronisation de la base élèves avec Supabase.")
                    except Exception as e:
                        st.error(f"❌ Une erreur est survenue : {e}")
                        
                st.markdown("##### Aperçu consolidé de la répartition")
                st.dataframe(df_eff, use_container_width=True)
            else:
                st.info("Données insuffisantes pour afficher la répartition par classe.")

elif st.session_state.espace_actif == "👨‍🏫 Espace Professeurs / Maîtres":
    st.markdown(
        '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Espace Enseignants & Saisie Pédagogique Locale</div>',
        unsafe_allow_html=True,
    )
    with st.form("form_note"):
        st.subheader("Enregistrer une note")
        eleve = st.text_input("Nom de l'élève")
        note = st.number_input("Note sur 20", min_value=0.0, max_value=20.0, step=0.5)
        submit_note = st.form_submit_button("Envoyer dans Supabase")
        
        if submit_note and eleve:
            try:
                supabase.table("notes").insert({"nom_eleve": eleve, "note": note}).execute()
                st.success("Note enregistrée avec succès dans Supabase !")
            except Exception as e:
                st.error(f"Erreur lors de l'enregistrement : {e}")

    st.markdown("### Notes enregistrées (Temps réel)")
    try:
        notes_data = supabase.table("notes").select("*").execute()
        if notes_data.data:
            st.dataframe(notes_data.data)
        else:
            st.info("Aucune note pour le moment.")
    except Exception as e:
        st.warning("Impossible de charger les données pour l'instant.")

elif st.session_state.espace_actif == "👨‍👩‍👧 Espace Parents / Élèves":
    st.markdown(
        '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Espace Parents - Suivi de l\'élève</div>',
        unsafe_allow_html=True,
    )
    st.info("Consultez ici les devoirs et les notes de vos enfants synchronisés en temps réel.")
    try:
        notes_data = supabase.table("notes").select("*").execute()
        if notes_data.data:
            st.dataframe(notes_data.data)
    except Exception:
        pass

elif st.session_state.espace_actif == "🔒 Espace Administration (Sécurisé)":
    st.markdown(
        '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Espace Administration - Connexion Sécurisée</div>',
        unsafe_allow_html=True,
    )
    if not st.session_state.authenticated_admin:
        with st.form("admin_login_form"):
            email_input = st.text_input("Email administrateur")
            password_input = st.text_input("Mot de passe", type="password")
            submitted = st.form_submit_button("Se connecter")
            if submitted:
                if email_input == ADMIN_EMAIL and password_input == "cpnm2026":
                    st.session_state.authenticated_admin = True
                    st.success("Connexion administrateur réussie !")
                    st.rerun()
                else:
                    st.error("Identifiants incorrects.")
    else:
        st.success("Vous êtes connecté en tant qu'Administrateur.")
        if st.button("Se déconnecter"):
            st.session_state.authenticated_admin = False
            st.rerun()
