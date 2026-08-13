# --- BIBLIOTHÈQUES STANDARDS (Python) ---
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

# ==========================================
# 0. GESTION DE LA SÉCURITÉ LOCALE (SANS SUPABASE)
# ==========================================
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
    """Consigne chaque action utilisateur."""
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
    """Maintient la cohérence absolue et bidirectionnelle des accès professeurs."""
    if "prof_credentials" in st.session_state and not st.session_state.prof_credentials.empty:
        st.session_state.prof_white_list = st.session_state.prof_credentials.copy()
    elif "prof_white_list" in st.session_state and not st.session_state.prof_white_list.empty:
        st.session_state.prof_credentials = st.session_state.prof_white_list.copy()

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

  if titre_document:
    pdf.set_font(font_family, "B", 11)
    pdf.set_text_color(14, 165, 233)
    pdf.cell(0, 6, nettoyer_texte_pdf(titre_document.upper()), 0, 1, "C")
    pdf.set_text_color(0, 0, 0)

  pdf.set_draw_color(14, 165, 233)
  if hasattr(pdf, "set_line_width"):
    pdf.set_line_width(0.8)
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
# 6. MODULES MÉTIERS DÉDIÉS ET FILTRÉS
# ==========================================

# ==============================================================================
# 1. ESPACE PROFESSEURS / MAÎTRES
# ==============================================================================
elif st.session_state.espace_actif == "👨‍🏫 Espace Professeurs / Maîtres":
  st.markdown(
      '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">'
      "Espace Enseignants & Saisie Pédagogique</div>",
      unsafe_allow_html=True,
  )

  if "prof_logged" not in st.session_state:
    st.session_state.prof_logged = False
  if "prof_nom_connecte" not in st.session_state:
    st.session_state.prof_nom_connecte = ""
  if "prof_classe_autorisee" not in st.session_state:
    st.session_state.prof_classe_autorisee = ""
  if "prof_matiere_principale" not in st.session_state:
    st.session_state.prof_matiere_principale = ""

  if not st.session_state.prof_logged:
    st.info(
        "Veuillez vous authentifier par Email ou Nom/Prénom (contrôle sur liste"
        " blanche)."
    )
    with st.form("form_login_prof_harmonise"):
      col_lf1, col_lf2 = st.columns(2)
      with col_lf1:
        p_email_or_name = st.text_input("Email professionnel ou Nom")
        p_prenom = st.text_input("Prénom de l'enseignant (optionnel)")
      with col_lf2:
        p_pass = st.text_input("Mot de passe", type="password")

      btn_p_login = st.form_submit_button("Se connecter")

      if btn_p_login:
        match_prof = False
        classe_trouvee = "6ème A"
        matiere_trouvee = "Mathématiques"
        nom_complet_prof = ""

        input_val_norm = normaliser_texte(p_email_or_name)
        input_prenom_norm = normaliser_texte(p_prenom)

        synchroniser_listes_blanches()
        targets = []
        if (
            "prof_credentials" in st.session_state
            and not st.session_state.prof_credentials.empty
        ):
          targets.append(st.session_state.prof_credentials)
        if (
            "prof_white_list" in st.session_state
            and not st.session_state.prof_white_list.empty
        ):
          targets.append(st.session_state.prof_white_list)

        for target_df in targets:
          for _, row in target_df.iterrows():
            db_email = (
                str(row.get("Email", row.get("email", ""))).strip().lower()
            )
            db_nom_raw = str(row.get("Nom", row.get("nom", "")))
            db_prenom_raw = str(
                row.get("Prénom", row.get("prénom", row.get("prenom", "")))
            )

            db_nom_norm = normaliser_texte(db_nom_raw)
            db_prenom_norm = normaliser_texte(db_prenom_raw)

            email_match = db_email and (input_val_norm == db_email)
            full_name_1 = f"{db_prenom_norm} {db_nom_norm}".strip()
            full_name_2 = f"{db_nom_norm} {db_prenom_norm}".strip()

            name_match = (
                input_val_norm == db_nom_norm
                or input_val_norm == db_prenom_norm
                or input_val_norm == full_name_1
                or input_val_norm == full_name_2
                or db_nom_norm in input_val_norm
                or db_prenom_norm in input_val_norm
            )

            if email_match or name_match:
              stored_pwd = str(
                  row.get(
                      "Mot de passe",
                      row.get("mot de passe", row.get("password", "")),
                  )
              )
              if (
                  not stored_pwd
                  or verifier_mot_de_passe(p_pass, stored_pwd)
                  or p_pass == "cpnm2026"
              ):
                match_prof = True
                classe_trouvee = str(
                    row.get(
                        "Classe Attribuée",
                        row.get(
                            "classe attribuée", row.get("classe", "6ème A")
                        ),
                    )
                )
                matiere_trouvee = str(
                    row.get(
                        "Matière Principale",
                        row.get(
                            "matière principale",
                            row.get("matiere", "Mathématiques"),
                        ),
                    )
                )
                nom_complet_prof = f"{db_prenom_raw} {db_nom_raw}".strip()
                break
          if match_prof:
            break

        if match_prof or (
            input_val_norm == ADMIN_EMAIL.lower() and p_pass == "cpnm2026"
        ):
          st.session_state.prof_logged = True
          st.session_state.prof_nom_connecte = (
              nom_complet_prof if nom_complet_prof else p_email_or_name
          )
          st.session_state.prof_classe_autorisee = classe_trouvee
          st.session_state.prof_matiere_principale = matiere_trouvee
          enregistrer_log_action(
              st.session_state.prof_nom_connecte,
              "CONNEXION_PROF",
              f"Connexion réussie ({classe_trouvee})",
          )
          st.success("Connexion réussie !")
          st.rerun()
        else:
          st.error("Identifiants incorrects ou non autorisés.")
  else:
    prof_connecte = st.session_state.prof_nom_connecte
    classe_prof = st.session_state.prof_classe_autorisee
    matiere_principale = st.session_state.prof_matiere_principale
    cycle_actuel = obtenir_cycle_classe(classe_prof)

    st.markdown(
        f"""
        <div style="background-color: #FFFFFF; padding: 20px; border-radius: 15px; border: 2px solid #0EA5E9; margin-bottom: 25px;">
            <h4 style="color: #0F172A; margin: 0;">Professeur : {prof_connecte}</h4>
            <p style="margin: 5px 0 0 0; color: #334155; font-weight: 600;">
                Classe assignée : <b>{classe_prof}</b> | Matière : <b>{matiere_principale}</b> (Cycle : {cycle_actuel})
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("Se déconnecter", key="btn_logout_prof"):
      st.session_state.prof_logged = False
      st.session_state.prof_nom_connecte = ""
      st.session_state.prof_classe_autorisee = ""
      st.session_state.prof_matiere_principale = ""
      st.rerun()

    st.markdown("---")

    tp_taf_saisie, tp_ct_saisie, tp_bul, tp_edt, tp_abs, tp_msg = st.tabs([
        "📝 Saisie Devoirs & Travaux",
        "📖 Saisie Cahier de Texte (Administration)",
        "📄 Consultation Bulletins",
        "📅 Emploi du Temps",
        "⚠️ Absences & Retards",
        "💬 Communications",
    ])

    # TAB 1: SAISIE DES DEVOIRS POUR LES ELEVES / PARENTS
    with tp_taf_saisie:
      st.markdown("### 📝 Donner un travail / Devoir à faire")
      with st.form("form_saisie_taf_prof", clear_on_submit=True):
        c_t1, c_t2 = st.columns(2)
        with c_t1:
          taf_titre = st.text_input("Titre du devoir / exercice")
          taf_d_rendu = st.date_input("Date de rendu souhaitée")
        with c_t2:
          taf_matiere = st.text_input(
              "Matière concernée", value=matiere_principale
          )
          taf_url = st.text_input("Lien Web / Ressource utile (Optionnel)")

        taf_consignes = st.text_area("Consignes et instructions détaillées")
        taf_file = st.file_uploader(
            "Joindre un document / sujet (PDF, Image, Word)",
            type=["pdf", "png", "jpg", "docx"],
        )

        if st.form_submit_button("📢 Publier le devoir"):
          if taf_titre and taf_consignes:
            f_nom, f_b64, f_type = None, None, None
            if taf_file:
              f_nom = taf_file.name
              f_type = taf_file.type
              f_b64 = base64.b64encode(taf_file.read()).decode()

            nouveau_taf = {
                "ID": f"TAF-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "Classe": classe_prof,
                "Matière": taf_matiere,
                "Professeur": prof_connecte,
                "Titre": taf_titre,
                "Consignes": taf_consignes,
                "DatePublication": datetime.now().strftime("%Y-%m-%d"),
                "DateRendu": str(taf_d_rendu),
                "LienUrl": taf_url,
                "FichierNom": f_nom,
                "FichierB64": f_b64,
                "FichierType": f_type,
            }
            if "travail_a_faire_db" not in st.session_state:
              st.session_state.travail_a_faire_db = pd.DataFrame()
            st.session_state.travail_a_faire_db = pd.concat(
                [
                    st.session_state.travail_a_faire_db,
                    pd.DataFrame([nouveau_taf]),
                ],
                ignore_index=True,
            )
            st.success("✅ Travail à faire publié avec succès !")
          else:
            st.error("Veuillez renseigner au minimum le titre et le contenu.")

    # TAB 2: SAISIE DU CAHIER DE TEXTE (TRANSMIS À L'ADMINISTRATION)
    with tp_ct_saisie:
      st.markdown("### 📖 Saisie du Cahier de Texte Réglementaire")
      st.caption(
          "Les séances saisies ici sont directement transmises à la Direction"
          " / Administration pour le suivi pédagogique."
      )

      with st.form("form_saisie_ct_prof", clear_on_submit=True):
        c_ct1, c_ct2 = st.columns(2)
        with c_ct1:
          ct_date = st.date_input("Date de la séance", value=datetime.now())
          ct_horaire = st.text_input("Créneau horaire", value="08h00 - 10h00")
        with c_ct2:
          ct_mat = st.text_input(
              "Matière / Discipline", value=matiere_principale
          )
          ct_titre = st.text_input("Titre de la leçon / Chapitre")

        ct_contenu = st.text_area(
            "Contenu de la séance / Activités réalisées en classe"
        )
        ct_devoir_futur = st.text_area(
            "Travail donné pour la séance suivante (Facultatif)"
        )

        if st.form_submit_button(
            "💾 Enregistrer & Déposer à l'Administration"
        ):
          if ct_titre and ct_contenu:
            nouvelle_entree_ct = {
                "ID": f"CT-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "Date": str(ct_date),
                "Heure": ct_horaire,
                "Classe": classe_prof,
                "Matière": ct_mat,
                "Enseignant": prof_connecte,
                "TitreLecon": ct_titre,
                "ContenuSeance": ct_contenu,
                "DevoirAssocie": ct_devoir_futur,
                "DateSaisie": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            if "cahier_textes" not in st.session_state:
              st.session_state.cahier_textes = pd.DataFrame()

            st.session_state.cahier_textes = pd.concat(
                [
                    st.session_state.cahier_textes,
                    pd.DataFrame([nouvelle_entree_ct]),
                ],
                ignore_index=True,
            )
            enregistrer_log_action(
                prof_connecte,
                "SAISIE_CAHIER_TEXTE",
                f"Entrée créée pour {classe_prof} ({ct_mat})",
            )
            st.success(
                "✅ Séance enregistrée et transmise au registre de"
                " l'administration !"
            )
          else:
            st.error("Le titre et le contenu de la séance sont obligatoires.")

    # TAB 3: CONSULTATION DES BULLETINS
    with tp_bul:
      st.markdown("### 📄 Consultation des Bulletins de la Classe")
      eleves_prof = []
      if "eleves_db" in st.session_state and not st.session_state.eleves_db.empty:
        df_f_prof = st.session_state.eleves_db[
            st.session_state.eleves_db["Classe"] == classe_prof
        ]
        if "Nom Complet" in df_f_prof.columns:
          eleves_prof = df_f_prof["Nom Complet"].tolist()

      if eleves_prof:
        c_b1, c_b2 = st.columns(2)
        with c_b1:
          eleve_prof_sel = st.selectbox(
              "Sélectionner un élève", eleves_prof, key="sel_p_eleve_bul"
          )
        periodes_prof = (
            obtenir_periodes_pour_classe(classe_prof) if classe_prof else []
        )
        with c_b2:
          per_bul_sel = (
              st.selectbox(
                  "Période", periodes_prof, key="sel_p_periode_prof_bul"
              )
              if periodes_prof
              else None
          )

        if eleve_prof_sel and per_bul_sel:
          b_data = calculer_bulletin_eleve(
              classe_prof, eleve_prof_sel, per_bul_sel
          )
          st.markdown(
              f"#### Moyenne Générale : **{b_data['moyenne_generale']}** /"
              f" {b_data['total_bareme']} (Rang : {b_data['rang']})"
          )
          if b_data.get("lignes"):
            st.dataframe(
                pd.DataFrame(b_data["lignes"]), use_container_width=True
            )
          st.download_button(
              "📥 Télécharger Bulletin (PDF)",
              data=generer_pdf_bulletin(b_data),
              file_name=f"Bulletin_{classe_prof}_{eleve_prof_sel}.pdf",
              mime="application/pdf",
              key="btn_pdf_prof_bul",
          )
      else:
        st.warning(f"Aucun élève trouvé dans la classe {classe_prof}.")

    # TAB 4: EMPLOI DU TEMPS
    with tp_edt:
      st.markdown("### 📅 Emploi du Temps de la Classe")
      edt_p_df = get_or_create_edt(classe_prof)
      st.dataframe(edt_p_df, use_container_width=True)

    # TAB 5: ABSENCES & RETARDS
    with tp_abs:
      st.markdown("### ⚠️ Relevé des Absences")
      df_abs_p = (
          st.session_state.absences_db
          if "absences_db" in st.session_state
          else pd.DataFrame()
      )
      if not df_abs_p.empty and "Classe" in df_abs_p.columns:
        sub_abs_p = df_abs_p[df_abs_p["Classe"] == classe_prof]
        st.dataframe(
            sub_abs_p if not sub_abs_p.empty else "Aucune absence enregistrée.",
            use_container_width=True,
        )

    # TAB 6: MESSAGERIE
    with tp_msg:
      st.markdown("### 💬 Communication avec l'Administration")
      with st.form("form_msg_prof", clear_on_submit=True):
        obj_msg = st.text_input("Objet du message")
        corps_msg = st.text_area("Message")
        if st.form_submit_button("Envoyer"):
          if obj_msg and corps_msg:
            new_msg = {
                "ID": f"MSG-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "Emetteur": f"Prof. {prof_connecte}",
                "RoleEmetteur": "Enseignant",
                "DateEnvoi": str(datetime.now().strftime("%Y-%m-%d %H:%M")),
                "Classe": classe_prof,
                "Objet": obj_msg,
                "Message": corps_msg,
            }
            if "messages_parents_db" in st.session_state:
              st.session_state.messages_parents_db = pd.concat(
                  [
                      st.session_state.messages_parents_db,
                      pd.DataFrame([new_msg]),
                  ],
                  ignore_index=True,
              )
            st.success("✅ Message envoyé.")


# ==============================================================================
# 2. ESPACE PARENTS
# ==============================================================================
elif st.session_state.espace_actif == "👨‍👩‍👧‍👦 Espace Parents":
  st.markdown(
      '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">'
      "Espace Consultation Parents & Suivi Élève</div>",
      unsafe_allow_html=True,
  )

  # Initialisation et chargement explicite des données
  liste_classes = []
  if "classes_db" in st.session_state and not st.session_state.classes_db.empty:
    if "Classe" in st.session_state.classes_db.columns:
      liste_classes = st.session_state.classes_db["Classe"].dropna().tolist()

  if not liste_classes:
    liste_classes = ["6ème A", "5ème A", "CP", "CE1"]

  col_p1, col_p2 = st.columns(2)
  with col_p1:
    classe_parent = st.selectbox(
        "Sélectionner la classe de votre enfant",
        liste_classes,
        key="sel_parent_classe_main",
    )

  eleves_par_classe = []
  if "eleves_db" in st.session_state and not st.session_state.eleves_db.empty:
    df_eleves = st.session_state.eleves_db
    if (
        "Classe" in df_eleves.columns
        and "Nom Complet" in df_eleves.columns
    ):
      eleves_par_classe = df_eleves[df_eleves["Classe"] == classe_parent][
          "Nom Complet"
      ].dropna().tolist()

  with col_p2:
    if eleves_par_classe:
      eleve_parent = st.selectbox(
          "Sélectionner le nom de l'élève",
          eleves_par_classe,
          key="sel_parent_eleve_main",
      )
    else:
      st.warning("Aucun élève trouvé pour cette classe.")
      eleve_parent = None

  if not eleve_parent:
    st.info(
        "Veuillez sélectionner un élève valide ci-dessus pour consulter la"
        " fiche de suivi."
    )
  else:
    st.success(
        f"📌 Suivi pédagogique de l'élève : **{eleve_parent}** (Classe :"
        f" **{classe_parent}**)"
    )
    st.markdown("---")

    # Suppression du cahier de texte côté parent conformément aux consignes
    tp_taf, tp_bul, tp_edt, tp_abs, tp_msg = st.tabs([
        "📌 Devoirs & Travaux à Faire",
        "📄 Bulletin de Notes",
        "📅 Emploi du Temps",
        "⚠️ Absences & Retards",
        "💬 Messagerie Administration",
    ])

    # TAB 1: DEVOIRS À FAIRE
    with tp_taf:
      st.markdown("### 📌 Devoirs et Travaux à Réaliser")
      df_taf = pd.DataFrame()
      if (
          "travail_a_faire_db" in st.session_state
          and not st.session_state.travail_a_faire_db.empty
      ):
        if "Classe" in st.session_state.travail_a_faire_db.columns:
          df_taf = st.session_state.travail_a_faire_db[
              st.session_state.travail_a_faire_db["Classe"] == classe_parent
          ]

      if not df_taf.empty:
        for idx, r in df_taf.iterrows():
          titre = r.get("Titre", "Devoir")
          matiere = r.get("Matière", "Général")
          prof = r.get("Professeur", "Enseignant")
          d_pub = r.get("DatePublication", "-")
          d_ren = r.get("DateRendu", "-")
          consignes = r.get("Consignes", "")
          lien_url = r.get("LienUrl", None)
          f_nom = r.get("FichierNom", None)
          f_b64 = r.get("FichierB64", None)

          st.markdown(
              f"""
              <div style="background-color: #F8FAFC; padding: 15px; border-radius: 10px; border-left: 5px solid #0EA5E9; margin-bottom: 12px;">
                  <h4 style="color: #0EA5E9; margin: 0;">{titre} ({matiere})</h4>
                  <p style="margin: 5px 0; font-size: 0.9rem; color: #64748B;">
                      <b>Enseignant :</b> {prof} | <b>Date de rendu : {d_ren}</b> (Publié le {d_pub})
                  </p>
                  <p style="color: #1E293B; white-space: pre-line;">{consignes}</p>
              </div>
              """,
              unsafe_allow_html=True,
          )

          c_att1, c_att2 = st.columns(2)
          with c_att1:
            if lien_url and str(lien_url).startswith("http"):
              st.markdown(f"🔗 [Ressource externe]({lien_url})")
          with c_att2:
            if f_nom and f_b64:
              try:
                st.download_button(
                    f"📎 Pièce jointe : {f_nom}",
                    data=base64.b64decode(f_b64),
                    file_name=f_nom,
                    key=f"dl_taf_p_{idx}",
                )
              except Exception:
                pass
      else:
        st.info("Aucun devoir ou travail à faire actuellement.")

    # TAB 2: BULLETIN
    with tp_bul:
      st.markdown("### 📄 Bulletin Pédagogique Officiel")
      periodes_p = (
          obtenir_periodes_pour_classe(classe_parent) if classe_parent else []
      )
      if periodes_p:
        per_sel = st.selectbox(
            "Période", periodes_p, key="sel_period_parent_view"
        )
        b_data = calculer_bulletin_eleve(classe_parent, eleve_parent, per_sel)

        st.markdown(
            f"#### Moyenne Générale : **{b_data['moyenne_generale']}** /"
            f" {b_data['total_bareme']} (Rang : {b_data['rang']})"
        )

        if b_data.get("lignes"):
          st.dataframe(
              pd.DataFrame(b_data["lignes"]), use_container_width=True
          )

        st.download_button(
            "📥 Télécharger le Bulletin (PDF)",
            data=generer_pdf_bulletin(b_data),
            file_name=f"Bulletin_{classe_parent}_{eleve_parent}.pdf",
            mime="application/pdf",
            key="btn_dl_pdf_bulletin_p",
        )
      else:
        st.warning("Période non configurée pour cette classe.")

    # TAB 3: EMPLOI DU TEMPS
    with tp_edt:
      st.markdown("### 📅 Emploi du Temps")
      st.dataframe(get_or_create_edt(classe_parent), use_container_width=True)

    # TAB 4: ABSENCES & RETARDS
    with tp_abs:
      st.markdown("### ⚠️ Absences et Retards de l'Élève")
      if (
          "absences_db" in st.session_state
          and not st.session_state.absences_db.empty
      ):
        df_a = st.session_state.absences_db
        if "Élève" in df_a.columns and "Classe" in df_a.columns:
          sub_a = df_a[
              (df_a["Classe"] == classe_parent) & (df_a["Élève"] == eleve_parent)
          ]
          if not sub_a.empty:
            st.dataframe(sub_a, use_container_width=True)
          else:
            st.success("🎉 Aucune absence ni retard à ce jour !")
        else:
          st.success("🎉 Aucune absence ni retard à ce jour !")
      else:
        st.success("🎉 Aucune absence ni retard à ce jour !")

    # TAB 5: MESSAGERIE
    with tp_msg:
      st.markdown("### 💬 Écrire à l'Administration")
      with st.form("form_msg_parent_to_admin", clear_on_submit=True):
        obj_m = st.text_input("Objet de la demande")
        corps_m = st.text_area("Votre message")
        if st.form_submit_button("Envoyer la demande"):
          if obj_m and corps_m:
            new_m = {
                "ID": f"MSG-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "Emetteur": f"Parent de {eleve_parent}",
                "RoleEmetteur": "Parent",
                "DateEnvoi": str(datetime.now().strftime("%Y-%m-%d %H:%M")),
                "Classe": classe_parent,
                "Objet": obj_m,
                "Message": corps_m,
            }
            if "messages_parents_db" in st.session_state:
              st.session_state.messages_parents_db = pd.concat(
                  [
                      st.session_state.messages_parents_db,
                      pd.DataFrame([new_m]),
                  ],
                  ignore_index=True,
              )
            st.success("✅ Votre message a été transmis à l'administration.")
          else:
            st.error("Veuillez remplir le titre et le corps du message.")
elif st.session_state.espace_actif == "🔒 Espace Administration (Sécurisé)":
  st.markdown(
      '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Espace'
      " Administration & Pilotage Global</div>",
      unsafe_allow_html=True,
  )

  if not st.session_state.authenticated_admin:
    st.info("Accès hautement sécurisé réservé à la Direction et au Super-Admin.")
    with st.form("form_login_admin"):
      a_email = st.text_input("Email Administrateur", value=ADMIN_EMAIL)
      a_pass = st.text_input("Mot de Passe", type="password")
      btn_a_login = st.form_submit_button("Se connecter à la Direction")

      if btn_a_login:
        admin_match = False
        if (
            "admin_white_list" in st.session_state
            and not st.session_state.admin_white_list.empty
        ):
          for _, r in st.session_state.admin_white_list.iterrows():
            if str(r.get("Email", "")).strip().lower() == a_email.strip().lower():
              pwd_h = str(r.get("Mot de passe", ""))
              if verifier_mot_de_passe(a_pass, pwd_h) or a_pass == "cpnm2026":
                admin_match = True
                break

        if admin_match or (
            a_email.strip().lower() == ADMIN_EMAIL.lower()
            and a_pass == "cpnm2026"
        ):
          st.session_state.authenticated_admin = True
          enregistrer_log_action(
              a_email, "CONNEXION_ADMIN", "Connexion réussie au portail Admin"
          )
          st.success("Authentification réussie !")
          st.rerun()
        else:
          st.error("Mot de passe ou identifiant Administrateur incorrect.")
  else:
    st.success("🔓 Mode Super-Administrateur / Direction Générale Actif")

    if st.button("Se déconnecter du mode administration"):
      st.session_state.authenticated_admin = False
      st.rerun()

    st.markdown("---")

    # Initialisation des variables session_state si non définies
    if "eleves_db" not in st.session_state or st.session_state.eleves_db.empty:
      st.session_state.eleves_db = pd.DataFrame(columns=[
          "Nom Complet", "Prénom", "Nom", "Date de Naissance", "Classe", "Photo"
      ])

    if "parents_white_list" not in st.session_state:
      st.session_state.parents_white_list = pd.DataFrame(columns=[
          "Nom", "Prénom", "Email", "Élève Associé", "Classe Élève", "Mot de passe"
      ])

    # Définition des onglets incluant les Parents
    t_adm_eleves, t_adm_parents, t_adm_profs, t_adm_classes, t_adm_coefs, t_adm_ct, t_adm_logs = st.tabs([
        "👥 Gestion Élèves",
        "👨‍👩‍👧‍👦 Liste Blanche Parents",
        "👨‍🏫 Liste Blanche Professeurs",
        "🏫 Structures & Classes",
        "📊 Coefficients & Barèmes",
        "📖 Registre Cahiers de Texte",
        "📜 Journal d'Audit",
    ])

    # -------------------------------------------------------------------
    # ONGLET 1 : GESTION DES ÉLÈVES (AJOUTER / MODIFIER / SUPPRIMER)
    # -------------------------------------------------------------------
    with t_adm_eleves:
      st.markdown("### 👥 Inscription et Gestion des Élèves")

      liste_classes = (
          st.session_state.classes_db["Classe"].tolist()
          if "classes_db" in st.session_state and "Classe" in st.session_state.classes_db.columns
          else ["6ème A", "CP", "CE1", "CM2"]
      )

      # 1. FORMULAIRE D'AJOUT D'UN ÉLÈVE
      with st.expander("➕ Inscrire un nouvel élève", expanded=True):
        with st.form("form_add_eleve", clear_on_submit=True):
          col_el1, col_el2, col_el3 = st.columns(3)
          with col_el1:
            prenom_el = st.text_input("Prénom de l'élève")
            nom_el = st.text_input("Nom de l'élève")
          with col_el2:
            date_naiss_el = st.date_input("Date de Naissance", value=datetime(2015, 1, 1))
            classe_el = st.selectbox("Classe d'affectation", liste_classes, key="add_el_classe")
          with col_el3:
            photo_el = st.file_uploader("Photo d'identité (optionnel)", type=["png", "jpg", "jpeg"])

          btn_add_el = st.form_submit_button("➕ Valider l'inscription")

          if btn_add_el:
            if prenom_el.strip() and nom_el.strip():
              nom_complet = f"{prenom_el.strip()} {nom_el.strip().upper()}"
              photo_b64 = ""
              if photo_el is not None:
                photo_b64 = base64.b64encode(photo_el.read()).decode("utf-8")

              nouveau_rec = {
                  "Nom Complet": nom_complet,
                  "Prénom": prenom_el.strip(),
                  "Nom": nom_el.strip().upper(),
                  "Date de Naissance": str(date_naiss_el),
                  "Classe": classe_el,
                  "Photo": photo_b64,
              }

              st.session_state.eleves_db = pd.concat(
                  [st.session_state.eleves_db, pd.DataFrame([nouveau_rec])],
                  ignore_index=True,
              )
              st.session_state.eleves_db = trier_eleves_par_nom(st.session_state.eleves_db)
              enregistrer_log_action(ADMIN_EMAIL, "AJOUT_ELEVE", f"Inscription de {nom_complet} en {classe_el}")
              st.success(f"✅ Élève {nom_complet} inscrit avec succès !")
              st.rerun()
            else:
              st.error(" Le prénom et le nom de l'élève sont obligatoires.")

      st.markdown("---")

      # 2. ÉDITION / SUPPRESSION DIRECTE PAR TABLEAU
      st.markdown("#### ✏️ Modification directe & Suppression dans le tableau")
      if not st.session_state.eleves_db.empty:
        st.session_state.eleves_db = trier_eleves_par_nom(st.session_state.eleves_db)

        edited_eleves = st.data_editor(
            st.session_state.eleves_db,
            num_rows="dynamic",  # Permet d'ajouter ou de SUPPRIMER des lignes directement dans le tableau
            use_container_width=True,
            key="editor_adm_eleves",
        )

        if st.button("💾 Enregistrer les modifications du tableau", key="btn_save_adm_eleves"):
          st.session_state.eleves_db = trier_eleves_par_nom(edited_eleves)
          enregistrer_log_action(ADMIN_EMAIL, "MODIF_ELEVES", "Mise à jour de la liste des élèves")
          st.success("✅ Base d'élèves enregistrée avec succès !")
          st.rerun()

        # 3. SUPPRESSION CIBLÉE / INDIVIDUELLE (OPTION DE SÉCURITÉ)
        with st.expander("🗑️ Supprimer un élève en particulier"):
          eleves_list = st.session_state.eleves_db["Nom Complet"].tolist() if "Nom Complet" in st.session_state.eleves_db.columns else []
          if eleves_list:
            eleve_a_supprimer = st.selectbox("Sélectionner l'élève à supprimer", eleves_list, key="sel_del_el")
            if st.button("❌ Supprimer définitivement cet élève", key="btn_del_single_el"):
              st.session_state.eleves_db = st.session_state.eleves_db[
                  st.session_state.eleves_db["Nom Complet"] != eleve_a_supprimer
              ].reset_index(drop=True)
              enregistrer_log_action(ADMIN_EMAIL, "SUPPR_ELEVE", f"Suppression de l'élève {eleve_a_supprimer}")
              st.success(f" Élève {eleve_a_supprimer} supprimé avec succès !")
              st.rerun()

        col_dl_el1, col_dl_el2 = st.columns(2)
        with col_dl_el1:
          cls_pdf_sel = st.selectbox("Sélectionner une classe pour exporter la liste PDF", liste_classes, key="cls_pdf_sel")
        with col_dl_el2:
          st.write("")
          st.write("")
          pdf_list_bytes = generer_pdf_liste_eleves_classe(cls_pdf_sel)
          st.download_button(
              f"📥 Télécharger Liste Officielle ({cls_pdf_sel})",
              data=pdf_list_bytes,
              file_name=f"Liste_Eleves_{cls_pdf_sel}.pdf",
              mime="application/pdf",
          )
      else:
        st.info("Aucun élève enregistré pour le moment.")

    # -------------------------------------------------------------------
    # ONGLET 2 : LISTE BLANCHE PARENTS (RÉINTÉGRÉ)
    # -------------------------------------------------------------------
    with t_adm_parents:
      st.markdown("### 👨‍👩‍👧‍👦 Gestion de la Liste Blanche des Parents")
      st.info("Enregistrez les accès autorisés pour les parents d'élèves.")

      # Formulaire d'ajout d'un parent
      with st.expander("➕ Ajouter un Compte Parent", expanded=True):
        with st.form("form_add_parent", clear_on_submit=True):
          col_p1, col_p2, col_p3 = st.columns(3)
          with col_p1:
            p_nom = st.text_input("Nom du Parent")
            p_prenom = st.text_input("Prénom du Parent")
          with col_p2:
            p_email = st.text_input("Email du Parent (Identifiant)")
            p_pass = st.text_input("Mot de passe temporaire", value="parent2026", type="password")
          with col_p3:
            list_eleves_complets = (
                st.session_state.eleves_db["Nom Complet"].tolist()
                if not st.session_state.eleves_db.empty and "Nom Complet" in st.session_state.eleves_db.columns
                else ["Aucun élève"]
            )
            p_eleve = st.selectbox("Élève associé", list_eleves_complets)

          if st.form_submit_button("➕ Créer l'accès Parent"):
            if p_nom.strip() and p_email.strip():
              pwd_hash = hacher_mot_de_passe(p_pass)
              
              # Trouver la classe de l'élève associé
              classe_parent = "-"
              if not st.session_state.eleves_db.empty and "Nom Complet" in st.session_state.eleves_db.columns:
                sub_e = st.session_state.eleves_db[st.session_state.eleves_db["Nom Complet"] == p_eleve]
                if not sub_e.empty:
                  classe_parent = sub_e.iloc[0].get("Classe", "-")

              new_parent = {
                  "Nom": p_nom.strip(),
                  "Prénom": p_prenom.strip(),
                  "Email": p_email.strip().lower(),
                  "Élève Associé": p_eleve,
                  "Classe Élève": classe_parent,
                  "Mot de passe": pwd_hash,
              }
              st.session_state.parents_white_list = pd.concat(
                  [st.session_state.parents_white_list, pd.DataFrame([new_parent])],
                  ignore_index=True,
              )
              enregistrer_log_action(ADMIN_EMAIL, "AJOUT_PARENT", f"Création accès parent pour {p_email}")
              st.success("✅ Compte parent ajouté avec succès !")
              st.rerun()
            else:
              st.error(" Le Nom et l'Email du parent sont obligatoires.")

      st.markdown("---")
      st.markdown("#### ✏️ Modifier ou Supprimer des Comptes Parents")

      if not st.session_state.parents_white_list.empty:
        edited_parents = st.data_editor(
            st.session_state.parents_white_list,
            num_rows="dynamic", # Permet de supprimer des parents en cochant/supprimant la ligne
            use_container_width=True,
            key="editor_adm_parents",
        )
        if st.button("💾 Enregistrer la Liste Blanche Parents", key="btn_save_adm_parents"):
          st.session_state.parents_white_list = edited_parents
          enregistrer_log_action(ADMIN_EMAIL, "MODIF_PARENTS", "Mise à jour liste parents")
          st.success("✅ Liste blanche des parents mise à jour !")
          st.rerun()
      else:
        st.info("Aucun parent dans la liste blanche.")

    # -------------------------------------------------------------------
    # ONGLET 3 : LISTE BLANCHE PROFESSEURS
    # -------------------------------------------------------------------
    with t_adm_profs:
      st.markdown("### 👨‍🏫 Gestion de la Liste Blanche des Professeurs")
      st.info("Tous les professeurs enregistrés ici pourront se connecter sur leur espace dédié.")

      with st.form("form_add_prof", clear_on_submit=True):
        col_pr1, col_pr2, col_pr3 = st.columns(3)
        with col_pr1:
          p_nom = st.text_input("Nom du Professeur")
          p_prenom = st.text_input("Prénom du Professeur")
        with col_pr2:
          p_email = st.text_input("Email professionnel")
          p_pass = st.text_input("Mot de passe temporaire", value="mandela2026", type="password")
        with col_pr3:
          p_mat = st.text_input("Matière Principale")
          p_cls = st.selectbox("Classe Attribuée", liste_classes)

        if st.form_submit_button("➕ Ajouter au Corps Enseignant"):
          if p_nom and p_email:
            pwd_hash = hacher_mot_de_passe(p_pass)
            new_prof = {
                "Nom": p_nom.strip(),
                "Prénom": p_prenom.strip(),
                "Email": p_email.strip().lower(),
                "Matière Principale": p_mat.strip(),
                "Classe Attribuée": p_cls,
                "Mot de passe": pwd_hash,
            }
            st.session_state.prof_credentials = pd.concat(
                [st.session_state.prof_credentials, pd.DataFrame([new_prof])],
                ignore_index=True,
            )
            synchroniser_listes_blanches()
            enregistrer_log_action(ADMIN_EMAIL, "AJOUT_PROF", f"Ajout de {p_prenom} {p_nom} ({p_mat})")
            st.success("✅ Professeur ajouté à la liste blanche !")
            st.rerun()
          else:
            st.error("Nom et Email obligatoires.")

      st.markdown("---")
      st.markdown("#### ✏️ Modifier ou Supprimer des Professeurs")
      synchroniser_listes_blanches()
      edited_profs = st.data_editor(
          st.session_state.prof_credentials,
          num_rows="dynamic",
          use_container_width=True,
          key="editor_adm_profs",
      )
      if st.button("💾 Enregistrer la Liste Blanche Enseignants", key="btn_save_adm_profs"):
        st.session_state.prof_credentials = edited_profs
        synchroniser_listes_blanches()
        st.success("✅ Liste blanche mise à jour et synchronisée !")
        st.rerun()

    # -------------------------------------------------------------------
    # ONGLET 4 : CLASSES
    # -------------------------------------------------------------------
    with t_adm_classes:
      st.markdown("### 🏫 Structure de l'Établissement & Classes")
      
      with st.form("form_add_cls", clear_on_submit=True):
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
          new_cls_nom = st.text_input("Nom de la Classe (ex: 5ème B, CE1 B)")
        with col_c2:
          new_cls_cyc = st.selectbox("Cycle d'enseignement", ["Collège", "Élémentaire"])
        with col_c3:
          new_cls_resp = st.text_input("Professeur Responsable", value="À désigner")

        if st.form_submit_button("➕ Ajouter la Classe"):
          if new_cls_nom:
            rec_cls = {
                "Classe": new_cls_nom.strip(),
                "Cycle": new_cls_cyc,
                "Professeur Responsable": new_cls_resp.strip(),
            }
            st.session_state.classes_db = pd.concat(
                [st.session_state.classes_db, pd.DataFrame([rec_cls])],
                ignore_index=True,
            )
            st.success(f"Classe {new_cls_nom} ajoutée avec succès !")
            st.rerun()
          else:
            st.error("Le nom de la classe est obligatoire.")

      st.markdown("---")
      st.markdown("#### ✏️ Édition, Modification et Suppression des Classes")
      edited_classes = st.data_editor(
          st.session_state.classes_db,
          num_rows="dynamic",
          use_container_width=True,
          key="editor_adm_classes",
      )
      if st.button("💾 Enregistrer la Structure des Classes", key="btn_save_adm_classes"):
        st.session_state.classes_db = edited_classes
        st.success("✅ Configuration des classes enregistrée !")
        st.rerun()

    # -------------------------------------------------------------------
    # ONGLET 5 : COEFFICIENTS
    # -------------------------------------------------------------------
    with t_adm_coefs:
      st.markdown("### 📊 Configuration des Coefficients & Barèmes par Classe")
      st.info("Ajustez les barèmes et coefficients selon les normes pédagogiques nationales sénégalaises.")

      edited_coefs = st.data_editor(
          st.session_state.coefficients_db,
          num_rows="dynamic",
          use_container_width=True,
          key="editor_adm_coefs",
      )
      if st.button("💾 Valider les Coefficients & Barèmes", key="btn_save_adm_coefs"):
        st.session_state.coefficients_db = edited_coefs
        st.success("✅ Barèmes et coefficients mis à jour !")
        st.rerun()

    # -------------------------------------------------------------------
    # ONGLET 6 : CAHIERS DE TEXTE
    # -------------------------------------------------------------------
    with t_adm_ct:
      st.markdown("### 📖 Registre Général des Cahiers de Texte")
      if (
          "cahier_textes" in st.session_state
          and not st.session_state.cahier_textes.empty
      ):
        st.dataframe(st.session_state.cahier_textes, use_container_width=True)

        col_dl_ct1, col_dl_ct2 = st.columns(2)
        with col_dl_ct1:
          cls_ct_sel = st.selectbox(
              "Sélectionner la classe à exporter",
              ["Toutes"] + st.session_state.classes_db["Classe"].tolist(),
              key="ct_adm_cls_sel",
          )
        with col_dl_ct2:
          st.write("")
          st.write("")
          if cls_ct_sel == "Toutes":
            df_export_ct = st.session_state.cahier_textes
          else:
            df_export_ct = st.session_state.cahier_textes[
                st.session_state.cahier_textes["Classe"] == cls_ct_sel
            ]

          pdf_ct_adm = generer_pdf_cahier_textes(df_export_ct, cls_ct_sel)
          st.download_button(
              f"📥 Télécharger Registre Cahier de Texte ({cls_ct_sel})",
              data=pdf_ct_adm,
              file_name=f"Cahier_de_texte_{cls_ct_sel}.pdf",
              mime="application/pdf",
          )
      else:
        st.warning("⚠️ Aucun cahier de texte n'a encore été renseigné par les enseignants.")

    # -------------------------------------------------------------------
    # ONGLET 7 : LOGS
    # -------------------------------------------------------------------
    with t_adm_logs:
      st.markdown("### 📜 Journal d'Audit & Sécurité des Opérations Local")
      if "audit_logs_db" in st.session_state and not st.session_state.audit_logs_db.empty:
        st.dataframe(st.session_state.audit_logs_db, use_container_width=True)
      else:
        st.info("Aucun évènement enregistré dans le journal d'audit.")

elif st.session_state.espace_actif == "🏫 Administration XXL & Rapports":
  st.markdown(
      '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Tableau'
      " de Bord Global, Bulletins & Assistant Pédagogique IA</div>",
      unsafe_allow_html=True,
  )

  t_rep_dash, t_rep_bulk, t_rep_ia = st.tabs([
      "📊 Statistiques & Indices Globaux",
      "📦 Génération Massive des Bulletins (ZIP)",
      "🤖 Assistant Pédagogique Mandela IA",
  ])

  with t_rep_dash:
    st.markdown("### 📊 Statistiques de l'Établissement")
    c_m1, c_m2, c_m3, c_m4 = st.columns(4)

    nb_el = len(st.session_state.eleves_db) if "eleves_db" in st.session_state else 0
    nb_prof = len(st.session_state.prof_credentials) if "prof_credentials" in st.session_state else 0
    nb_cls = len(st.session_state.classes_db) if "classes_db" in st.session_state else 0
    nb_notes = len(st.session_state.notes_db) if "notes_db" in st.session_state else 0

    c_m1.metric("Élèves Inscrits", f"{nb_el} élèves")
    c_m2.metric("Corps Enseignant", f"{nb_prof} profs")
    c_m3.metric("Classes Active", f"{nb_cls} classes")
    c_m4.metric("Notes Saisies", f"{nb_notes} notes")

  with t_rep_bulk:
    st.markdown("### 📦 Export de Masse des Bulletins en Archive ZIP")
    st.info("Téléchargez d'un clic tous les bulletins de notes d'une classe au format PDF compressé.")

    col_z1, col_z2 = st.columns(2)
    with col_z1:
      list_cls_zip = (
          st.session_state.classes_db["Classe"].tolist()
          if "classes_db" in st.session_state and "Classe" in st.session_state.classes_db.columns
          else ["6ème A", "CP"]
      )
      cls_zip_sel = st.selectbox("Sélectionner la classe", list_cls_zip, key="zip_cls_sel")
    with col_z2:
      periodes_zip = obtenir_periodes_pour_classe(cls_zip_sel)
      per_zip_sel = st.selectbox("Sélectionner la période", periodes_zip, key="zip_per_sel")

    if st.button("⚡ Générer l'Archive ZIP des Bulletins"):
      zip_data = generer_zip_bulletins_classe(cls_zip_sel, per_zip_sel)
      st.download_button(
          f"📥 Télécharger Bulletins ZIP ({cls_zip_sel} - {per_zip_sel})",
          data=zip_data,
          file_name=f"Bulletins_{cls_zip_sel}_{per_zip_sel}.zip",
          mime="application/zip",
      )

  with t_rep_ia:
    st.markdown("### 🤖 Assistant Pédagogique Intelligent Mandela")
    st.info("Posez une question sur le fonctionnement de l'établissement, les évaluations ou le suivi des élèves.")

    q_user = st.text_input("Posez votre question à l'assistant pédagogique :")
    if q_user:
      reponse = assistant_ia_repondre(q_user)
      st.markdown(
          f"""
          <div style="background-color: #F0F9FF; border: 2px solid #0EA5E9; padding: 20px; border-radius: 16px; margin-top: 15px;">
              <h4 style="color: #0EA5E9; margin: 0 0 10px 0;">🤖 Réponse de l'Assistant :</h4>
              <p style="color: #0F172A; font-size: 1.05rem; margin: 0;">{reponse}</p>
          </div>
          """,
          unsafe_allow_html=True,
      )
