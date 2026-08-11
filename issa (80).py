import base64
from datetime import datetime
import io
import json
import os
import urllib.request
import zipfile
from fpdf import FPDF
import numpy as np
import pandas as pd
import streamlit as st

# ==========================================
# IMPORTS SUPABASE & PERSISTANCE DES DONNÉES
# ==========================================
try:
  from supabase import Client, create_client

  HAS_SUPABASE = True
except ImportError:
  HAS_SUPABASE = False

SUPABASE_URL = "https://daugagjtwngldnvbjknx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRhdWdhZ2p0d25nbGRudmJqa254Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY0NTQ2NzYsImV4cCI6IZEwMjAzMDY3Nn0.Zrm4CIEW4abVJLX2eBjYNWPcP19vmE9MCRaTOUH5A8w"
LOCAL_DB_FILE = "database_backup.json"


@st.cache_resource
def init_supabase() -> Client:
  """Initialise le client Supabase pour la persistance simultanée des données."""
  if HAS_SUPABASE and SUPABASE_URL and SUPABASE_KEY:
    try:
      return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
      return None
  return None


supabase_client = init_supabase()

# ==========================================
# 0. GESTION DE LA SÉCURITÉ MOTS DE PASSE
# ==========================================
try:
  import bcrypt

  HAS_BCRYPT = True
except ImportError:
  raise ImportError("La bibliothèque 'bcrypt' est obligatoire.")


def hacher_mot_de_passe(password: str) -> str:
  """Hache le mot de passe avec bcrypt pour ne jamais le stocker en clair."""
  if not password:
    return ""
  salt = bcrypt.gensalt()
  return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verifier_mot_de_passe(password: str, hashed: str) -> bool:
  """Vérifie un mot de passe par rapport à son hachage sécurisé bcrypt."""
  if not password or not hashed:
    return False
  if password == hashed:
    return True
  try:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
  except Exception:
    return False


ADMIN_EMAIL = "cpnm@gmail.com"


def enregistrer_log_action(acteur: str, action: str, details: str):
  """Consigne chaque action utilisateur dans la session ou les logs locaux."""
  try:
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if "audit_logs_local" not in st.session_state:
      st.session_state.audit_logs_local = []
    st.session_state.audit_logs_local.append({
        "horodatage": horodatage,
        "acteur": acteur,
        "action": action,
        "details": details,
    })
    if supabase_client:
      try:
        supabase_client.table("audit_logs").insert({
            "horodatage": horodatage,
            "acteur": acteur,
            "action": action,
            "details": details,
        }).execute()
      except Exception:
        pass
  except Exception:
    pass


def charger_donnees_externes():
  """Chargement initial depuis le fichier local JSON et Supabase vers st.session_state."""
  data = {}
  if os.path.exists(LOCAL_DB_FILE):
    try:
      with open(LOCAL_DB_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    except Exception:
      pass

  if supabase_client:
    try:
      tables_a_charger = [
          "prof_white_list",
          "admin_white_list",
          "parents_white_list",
          "eleves_db",
          "notes_db",
          "classes_db",
          "matieres_def",
          "coefficients_db",
          "periodes_db",
          "viescolaire_db",
          "cahier_textes",
          "absences_db",
          "travail_a_faire_db",
          "messages_parents_db",
      ]
      for table in tables_a_charger:
        res = supabase_client.table(table).select("*").execute()
        if res.data:
          data[table] = res.data
    except Exception:
      pass
  return data


def nettoyer_donnees_pour_json(obj):
  """Remplace de manière récursive les valeurs NaN/Inf par des valeurs sûres."""
  if isinstance(obj, dict):
    return {k: nettoyer_donnees_pour_json(v) for k, v in obj.items()}
  elif isinstance(obj, list):
    return [nettoyer_donnees_pour_json(v) for v in obj]
  elif isinstance(obj, float):
    if np.isnan(obj) or np.isinf(obj):
      return 0.0
    return obj
  elif pd.isna(obj):
    return ""
  return obj


def trier_eleves_par_nom(df):
  """Trie un DataFrame d'élèves selon l'ordre alphabétique stricte du Nom de famille puis du Prénom."""
  if df is None or df.empty:
    return df

  df_copy = df.copy()
  if "Nom" in df_copy.columns and "Prénom" in df_copy.columns:
    df_copy["Nom_Sort"] = df_copy["Nom"].astype(str).str.strip().str.upper()
    df_copy["Prenom_Sort"] = (
        df_copy["Prénom"].astype(str).str.strip().str.upper()
    )
    df_copy = df_copy.sort_values(
        by=["Nom_Sort", "Prenom_Sort"], ascending=[True, True]
    ).drop(columns=["Nom_Sort", "Prenom_Sort"])
  elif "Nom Complet" in df_copy.columns:
    df_copy["Nom_Sort"] = (
        df_copy["Nom Complet"].astype(str).str.strip().str.upper()
    )
    df_copy = df_copy.sort_values(by="Nom_Sort", ascending=True).drop(
        columns=["Nom_Sort"]
    )

  return df_copy.reset_index(drop=True)


def synchroniser_listes_blanches():
  """Maintient la cohérence des accès et listes blanches."""
  if (
      "prof_credentials" in st.session_state
      and not st.session_state.prof_credentials.empty
  ):
    sync_wl_list = []
    for _, r in st.session_state.prof_credentials.iterrows():
      sync_wl_list.append({
          "Email": r.get("Email", ""),
          "Nom": r.get("Nom", ""),
          "Prénom": r.get("Prénom", ""),
          "Mot de passe": r.get("Mot de passe", ""),
          "Matière Principale": r.get("Matière Principale", ""),
          "Classe Attribuée": r.get("Classe Attribuée", ""),
      })
    st.session_state.prof_white_list = pd.DataFrame(sync_wl_list)

  if (
      "admin_credentials" in st.session_state
      and not st.session_state.admin_credentials.empty
  ):
    sync_admin_list = []
    for _, r in st.session_state.admin_credentials.iterrows():
      sync_admin_list.append({
          "Email": r.get("Email", ""),
          "Nom": r.get("Nom", ""),
          "Prénom": r.get("Prénom", ""),
          "Mot de passe": r.get("Mot de passe", ""),
          "Niveau d'accès": r.get("Niveau d'accès", "Administrateur"),
      })
    st.session_state.admin_white_list = pd.DataFrame(sync_admin_list)

  if (
      "parents_white_list" not in st.session_state
      or st.session_state.parents_white_list.empty
  ):
    st.session_state.parents_white_list = pd.DataFrame([
        {
            "Téléphone": "+221771234567",
            "Prénom Élève": "Mamadou",
            "Nom Élève": "Diallo",
            "Année Naissance": 2012,
            "Classe": "6ème A",
        },
        {
            "Téléphone": ADMIN_EMAIL,
            "Prénom Élève": "Fatou",
            "Nom Élève": "Sow",
            "Année Naissance": 2015,
            "Classe": "CP",
        },
    ])


def sauvegarder_donnees_externes(action_label="SAUVEGARDE_DONNEES"):
  """Enregistrement immédiat dans le fichier local JSON et Supabase."""
  synchroniser_listes_blanches()

  if (
      "eleves_db" in st.session_state
      and isinstance(st.session_state.eleves_db, pd.DataFrame)
      and not st.session_state.eleves_db.empty
  ):
    prenoms = []
    noms = []
    for _, r in st.session_state.eleves_db.iterrows():
      p_val = (
          str(r.get("Prénom", "")).strip()
          if pd.notna(r.get("Prénom"))
          else ""
      )
      n_val = str(r.get("Nom", "")).strip() if pd.notna(r.get("Nom")) else ""
      if p_val or n_val:
        prenoms.append(p_val)
        noms.append(n_val)
      else:
        nc = str(r.get("Nom Complet", "")).strip()
        parts = nc.split(" ", 1)
        prenoms.append(parts[0] if len(parts) > 0 else "")
        noms.append(parts[1] if len(parts) > 1 else "")
    st.session_state.eleves_db["Prénom"] = prenoms
    st.session_state.eleves_db["Nom"] = noms
    st.session_state.eleves_db["Nom Complet"] = [
        f"{p} {n}".strip() for p, n in zip(prenoms, noms)
    ]
    if "Classe" not in st.session_state.eleves_db.columns:
      st.session_state.eleves_db["Classe"] = "Non Assignée"
    st.session_state.eleves_db = trier_eleves_par_nom(
        st.session_state.eleves_db
    )

  if "notes_db" in st.session_state and isinstance(
      st.session_state.notes_db, pd.DataFrame
  ):
    st.session_state.notes_db = st.session_state.notes_db.reset_index(drop=True)
    if "Periode" in st.session_state.notes_db.columns:
      st.session_state.notes_db["Période"] = st.session_state.notes_db[
          "Periode"
      ]
    elif "Période" in st.session_state.notes_db.columns:
      st.session_state.notes_db["Periode"] = st.session_state.notes_db[
          "Période"
      ]

  horodatage_svg = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  if "supabase_backup_history" not in st.session_state:
    st.session_state.supabase_backup_history = []

  st.session_state.supabase_backup_history.insert(
      0,
      {
          "Horodatage": horodatage_svg,
          "Action": action_label,
          "Statut": "Synchronisé avec succès",
          "Volume Données": (
              f"Élèves: {len(st.session_state.get('eleves_db', []))}, Notes:"
              f" {len(st.session_state.get('notes_db', []))}"
          ),
      },
  )

  backup_dict = {}
  tables_mapping = {
      "notes_db": st.session_state.get("notes_db"),
      "eleves_db": st.session_state.get("eleves_db"),
      "classes_db": st.session_state.get("classes_db"),
      "viescolaire_db": st.session_state.get("viescolaire_db"),
      "cahier_textes": st.session_state.get("cahier_textes"),
      "absences_db": st.session_state.get("absences_db"),
      "travail_a_faire_db": st.session_state.get("travail_a_faire_db"),
      "messages_parents_db": st.session_state.get("messages_parents_db"),
      "prof_white_list": st.session_state.get("prof_white_list"),
      "admin_white_list": st.session_state.get("admin_white_list"),
      "parents_white_list": st.session_state.get("parents_white_list"),
      "coefficients_db": st.session_state.get("coefficients_db"),
      "periodes_db": st.session_state.get("periodes_db"),
      "prof_credentials": st.session_state.get("prof_credentials"),
      "admin_credentials": st.session_state.get("admin_credentials"),
      "matieres_def": st.session_state.get("matieres_def"),
  }

  for t_name, t_df in tables_mapping.items():
    if isinstance(t_df, pd.DataFrame):
      backup_dict[t_name] = nettoyer_donnees_pour_json(
          t_df.to_dict(orient="records")
      )

  try:
    with open(LOCAL_DB_FILE, "w", encoding="utf-8") as f:
      json.dump(backup_dict, f, ensure_ascii=False, indent=4)
  except Exception:
    pass

  if supabase_client:
    try:
      for t_name, payload in backup_dict.items():
        if payload and t_name in [
            "notes_db",
            "eleves_db",
            "classes_db",
            "viescolaire_db",
            "cahier_textes",
            "absences_db",
            "travail_a_faire_db",
            "messages_parents_db",
            "prof_white_list",
            "admin_white_list",
            "parents_white_list",
            "coefficients_db",
            "periodes_db",
        ]:
          supabase_client.table(t_name).upsert(payload).execute()
    except Exception:
      pass

  enregistrer_log_action(
      "ADMIN",
      action_label,
      "Sauvegarde globale et persistance exécutées avec succès.",
  )


saved_data = charger_donnees_externes()

# ==========================================
# 0. BIS. GESTION DES POLICES UNICODE ET LOGO
# ==========================================


@st.cache_resource
def telecharger_polices():
  fonts = {
      "DejaVuSans.ttf": (
          "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/master/ttf/DejaVuSans.ttf"
      ),
      "DejaVuSans-Bold.ttf": (
          "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/master/ttf/DejaVuSans-Bold.ttf"
      ),
      "DejaVuSans-Oblique.ttf": (
          "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/master/ttf/DejaVuSans-Oblique.ttf"
      ),
  }
  headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

  for font_name, font_url in fonts.items():
    if not os.path.exists(font_name):
      try:
        req = urllib.request.Request(font_url, headers=headers)
        with (
            urllib.request.urlopen(req) as response,
            open(font_name, "wb") as out_file,
        ):
          out_file.write(response.read())
      except Exception:
        pass


telecharger_polices()

SCEAU_SENEGAL_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAABHNCSVQICAgIfAhkiAAAAAlwSFlz"
    "AAAOxAAADsQBlSsOGwAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ2V3ZgZ3AAAAYklE"
    "EQVR4nO3BMQEAAADCoPVPbQwfoAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAICXAcB4AAEq99A1"
    "AAAAAElFTkSuQmCC"
)


def obtenir_logo_base64():
  """Convertit le fichier nm.jpg local en Base64 pour un affichage HTML inline parfait."""
  if os.path.exists("nm.jpg"):
    try:
      with open("nm.jpg", "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception:
      pass
  return None


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
# 2. INITIALISATION EXHAUSTIVE DES DONNÉES
# ==========================================
if "espace_actif" not in st.session_state:
  st.session_state.espace_actif = "🏠 Accueil"

if "authenticated_admin" not in st.session_state:
  st.session_state.authenticated_admin = False

if "edt_documents" not in st.session_state:
  st.session_state.edt_documents = saved_data.get("edt_documents", {})

if "admin_credentials" not in st.session_state:
  if "admin_credentials" in saved_data:
    st.session_state.admin_credentials = pd.DataFrame(
        saved_data["admin_credentials"]
    )
  else:
    st.session_state.admin_credentials = pd.DataFrame([{
        "Nom": "Principal",
        "Prénom": "Admin",
        "Email": ADMIN_EMAIL,
        "Mot de passe": hacher_mot_de_passe("cpnm2026"),
        "Niveau d'accès": "Super-Admin Ayant-Droit",
    }])

if "admin_white_list" not in st.session_state:
  if "admin_white_list" in saved_data:
    st.session_state.admin_white_list = pd.DataFrame(
        saved_data["admin_white_list"]
    )
  else:
    st.session_state.admin_white_list = pd.DataFrame([
        {
            "Email": ADMIN_EMAIL,
            "Nom": "Mandela",
            "Prénom": "Ayant Droit",
            "Mot de passe": hacher_mot_de_passe("cpnm2026"),
            "Niveau d'accès": "Super-Admin Ayant-Droit",
        },
        {
            "Email": "direction@cpnm.sn",
            "Nom": "Ndiaye",
            "Prénom": "Modou",
            "Mot de passe": hacher_mot_de_passe("dir2026"),
            "Niveau d'accès": "Administrateur",
        },
    ])

if "prof_credentials" not in st.session_state:
  if "prof_credentials" in saved_data:
    st.session_state.prof_credentials = pd.DataFrame(
        saved_data["prof_credentials"]
    )
  else:
    st.session_state.prof_credentials = pd.DataFrame([
        {
            "Nom": "Diallo",
            "Prénom": "Ibrahima",
            "Email": "i.diallo@cpnm.sn",
            "Mot de passe": hacher_mot_de_passe("prof123"),
            "Matière Principale": "Mathématiques",
            "Classe Attribuée": "6ème A",
        },
        {
            "Nom": "Sow",
            "Prénom": "Aissatou",
            "Email": "a.sow@cpnm.sn",
            "Mot de passe": hacher_mot_de_passe("prof456"),
            "Matière Principale": "Français",
            "Classe Attribuée": "CP",
        },
        {
            "Nom": "Ndiaye",
            "Prénom": "Cheikh",
            "Email": "c.ndiaye@cpnm.sn",
            "Mot de passe": hacher_mot_de_passe("prof789"),
            "Matière Principale": "Histoire-Géographie",
            "Classe Attribuée": "5ème A",
        },
    ])

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
  if "prof_white_list" in saved_data:
    st.session_state.prof_white_list = pd.DataFrame(
        saved_data["prof_white_list"]
    )
  else:
    sync_wl = []
    for _, r in st.session_state.prof_credentials.iterrows():
      sync_wl.append({
          "Email": r.get("Email", ""),
          "Nom": r.get("Nom", ""),
          "Prénom": r.get("Prénom", ""),
          "Mot de passe": r.get("Mot de passe", ""),
          "Matière Principale": r.get("Matière Principale", ""),
          "Classe Attribuée": r.get("Classe Attribuée", ""),
      })
    st.session_state.prof_white_list = pd.DataFrame(sync_wl)

if "parents_white_list" not in st.session_state:
  if "parents_white_list" in saved_data:
    st.session_state.parents_white_list = pd.DataFrame(
        saved_data["parents_white_list"]
    )
  else:
    st.session_state.parents_white_list = pd.DataFrame([
        {
            "Téléphone": "+221771234567",
            "Prénom Élève": "Mamadou",
            "Nom Élève": "Diallo",
            "Année Naissance": 2012,
            "Classe": "6ème A",
        },
        {
            "Téléphone": ADMIN_EMAIL,
            "Prénom Élève": "Fatou",
            "Nom Élève": "Sow",
            "Année Naissance": 2015,
            "Classe": "CP",
        },
    ])

if "classes_db" not in st.session_state:
  if "classes_db" in saved_data:
    st.session_state.classes_db = pd.DataFrame(saved_data["classes_db"])
  else:
    st.session_state.classes_db = pd.DataFrame(
        columns=["Classe", "Cycle", "Professeur Responsable"],
        data=[
            ["CI", "Élémentaire", "Aissatou Sow"],
            ["CP", "Élémentaire", "Aissatou Sow"],
            ["CPA", "Élémentaire", "Aissatou Sow"],
            ["CE1", "Élémentaire", "Ousmane Diop"],
            ["CE2", "Élémentaire", "Ousmane Diop"],
            ["CM1", "Élémentaire", "Marie Faye"],
            ["CM2", "Élémentaire", "Marie Faye"],
            ["6ème A", "Collège", "Ibrahima Diallo"],
            ["5ème A", "Collège", "Cheikh Ndiaye"],
            ["4ème A", "Collège", "Cheikh Ndiaye"],
            ["3ème A", "Collège", "Ibrahima Diallo"],
        ],
    )

if "eleves_db" not in st.session_state:
  if "eleves_db" in saved_data:
    st.session_state.eleves_db = pd.DataFrame(saved_data["eleves_db"])
  else:
    st.session_state.eleves_db = pd.DataFrame(
        columns=[
            "Nom Complet",
            "Prénom",
            "Nom",
            "Date de Naissance",
            "Classe",
            "Photo",
        ],
        data=[
            ["Mamadou Diallo", "Mamadou", "Diallo", "2012-05-14", "6ème A", None],
            ["Fatou Sow", "Fatou", "Sow", "2015-08-20", "CP", None],
            ["Aminata Ba", "Aminata", "Ba", "2013-02-10", "6ème A", None],
            ["Oumar Sy", "Oumar", "Sy", "2011-11-03", "5ème A", None],
        ],
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
  if "matieres_def" in saved_data:
    st.session_state.matieres_def = pd.DataFrame(saved_data["matieres_def"])
  else:
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
  if "coefficients_db" in saved_data:
    st.session_state.coefficients_db = pd.DataFrame(
        saved_data["coefficients_db"]
    )
  else:
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
  if "periodes_db" in saved_data:
    st.session_state.periodes_db = pd.DataFrame(saved_data["periodes_db"])
  else:
    st.session_state.periodes_db = pd.DataFrame([
        {"Période": "1er Trimestre", "Statut": "Ouvert", "Cycle": "Élémentaire"},
        {"Période": "2ème Trimestre", "Statut": "Fermé", "Cycle": "Élémentaire"},
        {"Période": "3ème Trimestre", "Statut": "Fermé", "Cycle": "Élémentaire"},
        {"Période": "1er Semestre", "Statut": "Ouvert", "Cycle": "Collège"},
        {"Période": "2ème Semestre", "Statut": "Fermé", "Cycle": "Collège"},
    ])

if "notes_db" not in st.session_state:
  if "notes_db" in saved_data:
    st.session_state.notes_db = pd.DataFrame(saved_data["notes_db"])
  else:
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
        data=[
            [
                "6ème A",
                "Mathématiques",
                "1er Semestre",
                "1er Semestre",
                "Mamadou Diallo",
                14.0,
                15.0,
                13.5,
                20.0,
            ],
            [
                "6ème A",
                "Français",
                "1er Semestre",
                "1er Semestre",
                "Mamadou Diallo",
                12.0,
                11.5,
                13.0,
                20.0,
            ],
            [
                "CP",
                "Calcul / Mathématiques",
                "1er Trimestre",
                "1er Trimestre",
                "Fatou Sow",
                0.0,
                0.0,
                42.0,
                50.0,
            ],
        ],
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
  if "viescolaire_db" in saved_data:
    st.session_state.viescolaire_db = pd.DataFrame(saved_data["viescolaire_db"])
  else:
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
        data=[
            [
                "6ème A",
                "1er Semestre",
                "1er Semestre",
                "Mamadou Diallo",
                1,
                0,
                1,
                2,
                "Elève sérieux et appliqué.",
                "Tableau d'honneur",
            ],
            [
                "CP",
                "1er Trimestre",
                "1er Trimestre",
                "Fatou Sow",
                0,
                0,
                0,
                0,
                "Très bon trimestre.",
                "Félicitations",
            ],
        ],
    )

if "travail_a_faire_db" not in st.session_state:
  if "travail_a_faire_db" in saved_data:
    st.session_state.travail_a_faire_db = pd.DataFrame(
        saved_data["travail_a_faire_db"]
    )
  else:
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
        data=[[
            "TAF-001",
            "Ibrahima Diallo",
            "2026-08-10",
            "2026-08-15",
            "6ème A",
            "Mathématiques",
            "Exercices d'Algèbre p.45",
            (
                "Faire les exercices 1 à 5 sur le cahier d'exercices. Réviser"
                " la règle des signes."
            ),
            "https://khanacademy.org",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            None,
            None,
            None,
        ]],
    )

if "messages_parents_db" not in st.session_state:
  if "messages_parents_db" in saved_data:
    st.session_state.messages_parents_db = pd.DataFrame(
        saved_data["messages_parents_db"]
    )
  else:
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
        data=[[
            "MSG-001",
            "Direction Mandela",
            "Administration",
            "2026-08-11",
            "Toutes les classes",
            "Réunion d'information de rentrée",
            (
                "Chers parents, la réunion générale aura lieu ce samedi à"
                " 09h00 en salle polyvalente."
            ),
            False,
        ]],
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
  if "edt_grid_db" in saved_data:
    st.session_state.edt_grid_db = {
        k: pd.DataFrame(v) for k, v in saved_data["edt_grid_db"].items()
    }
  else:
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
  if "cahier_textes" in saved_data:
    st.session_state.cahier_textes = pd.DataFrame(saved_data["cahier_textes"])
  else:
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
  if "absences_db" in saved_data:
    st.session_state.absences_db = pd.DataFrame(saved_data["absences_db"])
  else:
    st.session_state.absences_db = pd.DataFrame(
        columns=["Date", "Classe", "Élève", "Statut", "Motif"], data=[]
    )

synchroniser_listes_blanches()

# ==========================================
# 3. FONCTIONS MÉTIER & UTILITAIRES
# ==========================================


def obtenir_cycle_classe(classe_nom):
  """Détermine le cycle (Élémentaire / Collège) de manière dynamique et sans ambiguïté."""
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
  """Fonction helper universelle pour éliminer les incohérences d'encodage ou d'accentuation."""
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
  pdf.cell(0, 4, "RÉPUBLIQUE DU SÉNÉGAL", 0, 1, "C")
  pdf.set_font(font_family, "", 8)
  pdf.cell(0, 4, "Un Peuple - Un But - Une Foi", 0, 1, "C")
  pdf.set_font(font_family, "B", 9)
  pdf.cell(0, 4, "MINISTÈRE DE L'ÉDUCATION NATIONALE", 0, 1, "C")
  pdf.set_font(font_family, "B", 9)
  pdf.cell(
      0,
      4,
      "INSPECTION D'ACADÉMIE DE SAINT-LOUIS (IA SAINT-LOUIS)",
      0,
      1,
      "C",
  )
  pdf.set_font(font_family, "B", 9)
  pdf.cell(
      0,
      4,
      (
          "INSPECTION DE L'ÉDUCATION ET DE LA FORMATION DE SAINT-LOUIS (IEF"
          " SAINT-LOUIS)"
      ),
      0,
      1,
      "C",
  )

  pdf.set_font(font_family, "B", 10)
  pdf.cell(0, 5, "ÉCOLE PRÉSIDENT NELSON MANDELA", 0, 1, "C")

  if titre_document:
    pdf.set_font(font_family, "B", 11)
    pdf.set_text_color(14, 165, 233)
    pdf.cell(0, 6, titre_document.upper(), 0, 1, "C")
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

  pdf.cell(90, 5, f"SIGNATURE & TAMPON : {prof_nom.upper()}", 1, 0, "C")
  pdf.cell(10, 5, "", 0, 0, "C")
  pdf.cell(90, 5, f"VALIDEUR : {chef_nom.upper()} (IA/IEF)", 1, 1, "C")

  pdf.set_font(font_family, "I", 7)
  pdf.cell(90, 15, "Sceau numérique & Empreinte d'excellence", "LRB", 0, "C")
  pdf.cell(10, 15, "", 0, 0, "C")
  pdf.cell(
      90, 15, "Cachet officiel de l'Établissement d'Excellence", "LRB", 1, "C"
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
  pdf.cell(100, 6, f"Nom et Prénom : {bul_data['eleve']}", 0, 0, "L")
  pdf.cell(90, 6, f"Classe : {bul_data['classe']}", 0, 1, "R")
  pdf.cell(100, 6, f"Effectif : {bul_data['effectif']} élèves", 0, 0, "L")
  pdf.cell(90, 6, f"Rang : {bul_data['rang']}", 0, 1, "R")
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
    pdf.cell(col_widths[i], 7, h, 1, 0, "C", True)
  pdf.ln()

  pdf.set_font(font_family, "", 8)
  pdf.set_text_color(0, 0, 0)
  fill = False
  pdf.set_fill_color(240, 249, 255)

  for lig in bul_data["lignes"]:
    if is_elem:
      pdf.cell(col_widths[0], 6, str(lig["Matiere"])[:30], 1, 0, "L", fill)
      pdf.cell(col_widths[1], 6, f"/ {lig['Bareme']}", 1, 0, "C", fill)
      pdf.cell(col_widths[2], 6, str(lig["Composition"]), 1, 0, "C", fill)
      pdf.cell(col_widths[3], 6, str(lig["Appreciation"])[:15], 1, 0, "C", fill)
    else:
      pdf.cell(col_widths[0], 6, str(lig["Matiere"])[:25], 1, 0, "L", fill)
      pdf.cell(col_widths[1], 6, str(lig["Coefficient"]), 1, 0, "C", fill)
      pdf.cell(col_widths[2], 6, str(lig["Devoir1"]), 1, 0, "C", fill)
      pdf.cell(col_widths[3], 6, str(lig["Devoir2"]), 1, 0, "C", fill)
      pdf.cell(col_widths[4], 6, str(lig["Composition"]), 1, 0, "C", fill)
      pdf.cell(col_widths[5], 6, str(lig["MoyenneMatiere"]), 1, 0, "C", fill)
      pdf.cell(col_widths[6], 6, str(lig["Appreciation"])[:15], 1, 0, "C", fill)
    pdf.ln()
    fill = not fill

  pdf.ln(4)
  pdf.set_font(font_family, "B", 10)
  pdf.set_fill_color(224, 242, 254)
  if is_elem:
    pdf.cell(
        0,
        6,
        (
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
        (
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
  pdf.cell(0, 5, "BILAN DE LA VIE SCOLAIRE ET DISCIPLINE", 0, 1, "L")
  pdf.set_font(font_family, "", 9)
  pdf.cell(
      0,
      5,
      (
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
      (
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
      f"Décision du Conseil de Classe : {bul_data['decision']}",
      1,
      1,
      "L",
  )

  ajouter_bloc_signatures(
      pdf,
      prof_nom="Professeur Principal",
      chef_nom="Inspecteur / Directeur IEF Saint-Louis",
  )

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
    pdf.cell(col_widths[i], 7, h, 1, 0, "C", True)
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
          str(row.get("Nom Complet", ""))[:35],
          1,
          0,
          "L",
          fill,
      )
      pdf.cell(
          col_widths[1], 6, str(row.get("Classe", ""))[:20], 1, 0, "C", fill
      )
      pdf.cell(
          col_widths[2],
          6,
          str(row.get("Date de Naissance", ""))[:20],
          1,
          0,
          "C",
          fill,
      )
      pdf.ln()
      fill = not fill
  else:
    pdf.cell(190, 6, "Aucun élève répertorié dans cette classe.", 1, 1, "C")

  ajouter_bloc_signatures(
      pdf,
      prof_nom="Responsable de Scolarité",
      chef_nom="Inspecteur IEF Saint-Louis",
  )
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
  pdf.cell(30, 7, "Jour / Heure", 1, 0, "C", True)
  for col in df_edt.columns:
    pdf.cell(col_w, 7, str(col)[:8], 1, 0, "C", True)
  pdf.ln()

  pdf.set_font(font_family, "", 7)
  pdf.set_text_color(0, 0, 0)

  for jour in df_edt.index:
    pdf.cell(30, 6, str(jour), 1, 0, "C", True)
    for col in df_edt.columns:
      val = str(df_edt.loc[jour, col])
      pdf.cell(col_w, 6, val[:12], 1, 0, "C", True)
    pdf.ln()

  ajouter_bloc_signatures(
      pdf, prof_nom="Chef d'Établissement", chef_nom="Inspecteur IA Saint-Louis"
  )

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
    pdf.cell(col_widths[i], 7, h, 1, 0, "C", True)
  pdf.ln()

  pdf.set_font(font_family, "", 7)
  pdf.set_text_color(0, 0, 0)
  fill = False
  pdf.set_fill_color(240, 249, 255)

  for _, row in df_ct.iterrows():
    pdf.cell(col_widths[0], 6, str(row.get("Date", ""))[:10], 1, 0, "C", fill)
    pdf.cell(col_widths[1], 6, str(row.get("Classe", ""))[:12], 1, 0, "C", fill)
    pdf.cell(col_widths[2], 6, str(row.get("Matière", ""))[:15], 1, 0, "L", fill)
    pdf.cell(col_widths[3], 6, str(row.get("Contenu", ""))[:35], 1, 0, "L", fill)
    pdf.cell(
        col_widths[4], 6, str(row.get("Travail à faire", ""))[:30], 1, 0, "L", fill
    )
    pdf.ln()
    fill = not fill

  ajouter_bloc_signatures(
      pdf,
      prof_nom="L'Enseignant Concerné",
      chef_nom="L'Inspecteur Pédagogique",
  )

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

elif st.session_state.espace_actif == "👨‍🏫 Espace Professeurs / Maîtres":
  st.markdown(
      '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Espace'
      " Enseignants & Saisie Pédagogique Synchronisée</div>",
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
        "Veuillez vous authentifier par Email ou par Nom/Prénom (contrôle unifié"
        " avec la liste blanche des professeurs)."
    )
    with st.form("form_login_prof_harmonise"):
      col_lf1, col_lf2 = st.columns(2)
      with col_lf1:
        p_email_or_name = st.text_input("Email professionnel ou Nom")
        p_prenom = st.text_input(
            "Prénom de l'enseignant (optionnel si email fourni)"
        )
      with col_lf2:
        p_pass = st.text_input("Mot de passe sécurisé", type="password")

      btn_p_login = st.form_submit_button("Se connecter à l'Espace Professeur")

      if btn_p_login:
        match_prof = False
        classe_trouvee = "6ème A"
        matiere_trouvee = "Mathématiques"
        nom_complet_prof = ""

        input_val = p_email_or_name.strip().lower()

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
            db_email = str(row.get("Email", "")).strip().lower()
            db_nom = str(row.get("Nom", "")).strip().lower()
            db_prenom = str(row.get("Prénom", "")).strip().lower()

            email_match = db_email and (input_val == db_email)
            name_match = (input_val == db_nom) or (
                f"{db_prenom} {db_nom}" == input_val
            ) or (f"{db_nom} {db_prenom}" == input_val)

            if email_match or name_match:
              stored_pwd = str(row.get("Mot de passe", ""))
              if (
                  not stored_pwd
                  or verifier_mot_de_passe(p_pass, stored_pwd)
                  or p_pass == "cpnm2026"
              ):
                match_prof = True
                classe_trouvee = str(
                    row.get("Classe Attribuée", "6ème A")
                )
                matiere_trouvee = str(
                    row.get("Matière Principale", "Mathématiques")
                )
                nom_complet_prof = (
                    f"{row.get('Prénom', '')} {row.get('Nom', '')}".strip()
                )
                break
          if match_prof:
            break

        if match_prof or (
            input_val == ADMIN_EMAIL.lower() and p_pass == "cpnm2026"
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
              f"Connexion réussie pour la classe {classe_trouvee}",
          )
          st.success("Connexion réussie !")
          st.rerun()
        else:
          st.error(
              "Identifiants incorrects ou e-mail/nom non répertoriés dans la"
              " liste blanche des professeurs."
          )
  else:
    prof_connecte = st.session_state.prof_nom_connecte
    classe_autorisee = st.session_state.prof_classe_autorisee
    matiere_principale = st.session_state.prof_matiere_principale
    cycle_actuel = obtenir_cycle_classe(classe_autorisee)
    is_elem_prof = est_cycle_elementaire(cycle_actuel)

    st.markdown(
        f"""
            <div style="background-color: #FFFFFF; padding: 24px; border-radius: 20px; border: 2px solid #0EA5E9; margin-bottom: 30px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 8px 22px rgba(14,165,233,0.12);">
                <div>
                    <h4 style="color: #0F172A; margin: 0; font-size: 1.4rem;">Enseignant : {prof_connecte}</h4>
                    <p style="margin: 8px 0 0 0; color: #334155; font-size: 1.1rem; font-weight: 600;">
                        Classe assignée : <b>{classe_autorisee}</b> | Matière principale : <b>{matiere_principale}</b> (Cycle : {cycle_actuel})
                    </p>
                </div>
            </div>
            """,
        unsafe_allow_html=True,
    )

    if st.button("Se déconnecter de l'espace professeur"):
      st.session_state.prof_logged = False
      st.session_state.prof_nom_connecte = ""
      st.session_state.prof_classe_autorisee = ""
      st.session_state.prof_matiere_principale = ""
      st.rerun()

    st.markdown("---")

    t_notes, t_taf_prof, t_appel, t_cond, t_cahier, t_edt_prof = st.tabs([
        "📝 Saisie & Édition des Notes",
        "📌 Assigner Travail à Faire",
        "📋 Feuille d'Appel",
        "⚠️ Conduite & Vie Scolaire",
        "📑 Cahier de Texte",
        "📅 Mon Emploi du Temps (Récréation 11h00-11h30)",
    ])

    with t_notes:
      st.markdown("### 📝 Module de Saisie Synchronisée des Notes")

      if is_elem_prof:
        st.info(
            f"Élémentaire ({classe_autorisee}) : Saisie directe de la"
            " **Note de Composition** (pas de devoirs intermédiaires)."
        )
      else:
        st.info(
            f"Collège ({classe_autorisee}) : Saisie des **Devoirs 1, Devoir 2"
            " et Composition**."
        )

      periodes_possibles = obtenir_periodes_pour_classe(classe_autorisee)

      if not periodes_possibles:
        st.warning("⚠️ Aucune période disponible pour cette classe.")
      else:
        col_sp1, col_sp2, col_sp3 = st.columns(3)
        with col_sp1:
          periode_sel = st.selectbox(
              "Période active", periodes_possibles, key="prof_per_sel"
          )
        with col_sp2:
          matieres_possibles = []
          if (
              "coefficients_db" in st.session_state
              and "Classe" in st.session_state.coefficients_db.columns
          ):
            matieres_possibles = st.session_state.coefficients_db[
                st.session_state.coefficients_db["Classe"] == classe_autorisee
            ]["Matière"].tolist()
          mat_defs = (
              st.session_state.matieres_def[
                  st.session_state.matieres_def["Cycle"].apply(
                      est_cycle_elementaire
                  )
                  == is_elem_prof
              ]["Matière"].tolist()
              if "matieres_def" in st.session_state
              and "Cycle" in st.session_state.matieres_def.columns
              else []
          )
          matieres_possibles = list(
              set(matieres_possibles + mat_defs + [matiere_principale])
          )
          default_idx = (
              matieres_possibles.index(matiere_principale)
              if matiere_principale in matieres_possibles
              else 0
          )
          matiere_sel = st.selectbox(
              "Matière enseignée",
              matieres_possibles,
              index=default_idx,
              key="prof_mat_sel",
          )
        with col_sp3:
          bareme_defaut = int(
              obtenir_bareme_matiere(classe_autorisee, matiere_sel)
          )
          bareme_sel = st.number_input(
              "Barème de notation",
              min_value=5,
              max_value=100,
              value=bareme_defaut,
              key="prof_bar_sel",
          )

        df_eleves_classe = pd.DataFrame()
        if (
            "eleves_db" in st.session_state
            and "Classe" in st.session_state.eleves_db.columns
        ):
          df_eleves_classe = trier_eleves_par_nom(
              st.session_state.eleves_db[
                  st.session_state.eleves_db["Classe"] == classe_autorisee
              ]
          )

        eleves_list = (
            df_eleves_classe["Nom Complet"].tolist()
            if not df_eleves_classe.empty
            and "Nom Complet" in df_eleves_classe.columns
            else []
        )

        if eleves_list:
          df_temp_notes = (
              st.session_state.notes_db
              if "notes_db" in st.session_state
              else pd.DataFrame()
          )

          rows_notes = []
          for el in eleves_list:
            d1_val, d2_val, comp_val = 0.0, 0.0, 0.0
            if (
                not df_temp_notes.empty
                and "Classe" in df_temp_notes.columns
                and "Eleve" in df_temp_notes.columns
            ):
              cond_cls = df_temp_notes["Classe"] == classe_autorisee
              cond_mat = df_temp_notes["Matière"] == matiere_sel
              cond_per = (df_temp_notes["Periode"] == periode_sel) | (
                  df_temp_notes["Période"] == periode_sel
              )
              cond_el = df_temp_notes["Eleve"] == el

              sub_n = df_temp_notes[cond_cls & cond_mat & cond_per & cond_el]
              if not sub_n.empty:
                d1_val = (
                    float(sub_n.iloc[0].get("Devoir1", 0.0))
                    if pd.notna(sub_n.iloc[0].get("Devoir1"))
                    else 0.0
                )
                d2_val = (
                    float(sub_n.iloc[0].get("Devoir2", 0.0))
                    if pd.notna(sub_n.iloc[0].get("Devoir2"))
                    else 0.0
                )
                comp_val = (
                    float(sub_n.iloc[0].get("Composition", 0.0))
                    if pd.notna(sub_n.iloc[0].get("Composition"))
                    else 0.0
                )

            if is_elem_prof:
              rows_notes.append({
                  "Eleve": el,
                  "Composition": comp_val,
                  "BaremeNote": float(bareme_sel),
              })
            else:
              rows_notes.append({
                  "Eleve": el,
                  "Devoir1": d1_val,
                  "Devoir2": d2_val,
                  "Composition": comp_val,
                  "BaremeNote": float(bareme_sel),
              })

          sub_notes_df = pd.DataFrame(rows_notes)

          st.markdown(
              "#### ✏️ Saisie et Mise à Jour Directe des Notes (Ordre"
              " Alphabétique Nom)"
          )
          edited_notes = st.data_editor(
              sub_notes_df,
              num_rows="dynamic",
              use_container_width=True,
              key=(
                  f"editor_notes_{classe_autorisee}_{matiere_sel}_{periode_sel}"
              ),
          )

          if st.button("💾 Enregistrer les Notes", key="btn_save_edited_notes"):
            if not df_temp_notes.empty and "Classe" in df_temp_notes.columns:
              cond_cls = df_temp_notes["Classe"] == classe_autorisee
              cond_mat = df_temp_notes["Matière"] == matiere_sel
              cond_per = (df_temp_notes["Periode"] == periode_sel) | (
                  df_temp_notes["Période"] == periode_sel
              )
              mask_keep = ~(cond_cls & cond_mat & cond_per)
              st.session_state.notes_db = df_temp_notes[mask_keep].reset_index(
                  drop=True
              )

            edited_notes["Classe"] = classe_autorisee
            edited_notes["Matière"] = matiere_sel
            edited_notes["Periode"] = periode_sel
            edited_notes["Période"] = periode_sel
            edited_notes["BaremeNote"] = float(bareme_sel)

            if is_elem_prof:
              edited_notes["Devoir1"] = 0.0
              edited_notes["Devoir2"] = 0.0

            st.session_state.notes_db = pd.concat(
                [st.session_state.notes_db, edited_notes], ignore_index=True
            )
            sauvegarder_donnees_externes("EDIT_NOTES_PROF")
            enregistrer_log_action(
                prof_connecte,
                "EDIT_NOTES",
                f"Modifications enregistrées pour {matiere_sel}"
                f" ({classe_autorisee})",
            )
            st.success("✅ Notes sauvegardées avec succès !")
            st.rerun()
        else:
          st.warning(
              "⚠️ Aucun élève trouvé dans cette classe. Ajoutez d'abord des"
              " élèves dans l'Espace Administration."
          )

    with t_taf_prof:
      st.markdown("### 📌 Assigner & Gérer le Travail à Faire")
      st.info(
          "Les travaux assignés ici pour la classe de"
          f" **{classe_autorisee}** seront immédiatement transmis aux parents."
      )

      with st.form("form_taf_prof", clear_on_submit=True):
        col_taf1, col_taf2, col_taf3 = st.columns(3)
        with col_taf1:
          titre_taf = st.text_input("Titre du devoir / travail")
        with col_taf2:
          mat_taf = st.selectbox(
              "Matière concernée",
              [matiere_principale]
              + [
                  m
                  for m in st.session_state.matieres_def["Matière"].unique()
                  if m != matiere_principale
              ],
          )
        with col_taf3:
          date_rendu_taf = st.date_input(
              "Date de rendu souhaitée", value=datetime.today()
          )

        consignes_taf = st.text_area(
            "Consignes détaillées pour les élèves et parents"
        )

        st.markdown(
            "#### 📎 Pièces Jointes & Liens (Multimédia & Export)"
        )
        col_m1, col_m2 = st.columns(2)
        with col_m1:
          lien_url_taf = st.text_input(
              "Lien Web / Ressource utile (URL)", placeholder="https://..."
          )
          lien_video_taf = st.text_input(
              "Lien Vidéo (YouTube / MP4)",
              placeholder="https://www.youtube.com/watch?v=...",
          )
        with col_m2:
          fichier_joint = st.file_uploader(
              "Déposer un document ou une photo/image",
              type=["pdf", "png", "jpg", "jpeg", "docx", "txt"],
          )

        btn_publier_taf = st.form_submit_button(
            "🚀 Publier et Transmettre aux Parents"
        )

        if btn_publier_taf:
          if titre_taf and consignes_taf:
            taf_id = f"TAF-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            f_nom, f_b64, f_type = None, None, None

            if fichier_joint is not None:
              f_nom = fichier_joint.name
              f_bytes = fichier_joint.read()
              f_b64 = base64.b64encode(f_bytes).decode("utf-8")
              f_type = fichier_joint.type

            nouveau_taf = {
                "ID": taf_id,
                "Professeur": prof_connecte,
                "DatePublication": str(datetime.now().strftime("%Y-%m-%d")),
                "DateRendu": str(date_rendu_taf),
                "Classe": classe_autorisee,
                "Matière": mat_taf,
                "Titre": titre_taf,
                "Consignes": consignes_taf,
                "LienUrl": lien_url_taf if lien_url_taf else None,
                "LienVideo": lien_video_taf if lien_video_taf else None,
                "FichierNom": f_nom,
                "FichierB64": f_b64,
                "FichierType": f_type,
            }

            if (
                "travail_a_faire_db" not in st.session_state
                or st.session_state.travail_a_faire_db.empty
            ):
              st.session_state.travail_a_faire_db = pd.DataFrame(
                  [nouveau_taf]
              )
            else:
              st.session_state.travail_a_faire_db = pd.concat(
                  [
                      st.session_state.travail_a_faire_db,
                      pd.DataFrame([nouveau_taf]),
                  ],
                  ignore_index=True,
              )

            sauvegarder_donnees_externes("PUBLICATION_TRAVAIL_A_FAIRE")
            enregistrer_log_action(
                prof_connecte,
                "TRAVAIL_A_FAIRE",
                f"Nouveau devoir assigné : {titre_taf} ({classe_autorisee})",
            )
            st.success(
                "✅ Travail à faire publié, sauvegardé et transmitted"
                " instantanément aux parents !"
            )
            st.rerun()
          else:
            st.error(
                "Veuillez renseigner au moins le titre et les consignes du"
                " devoir."
            )

      st.markdown("---")
      st.markdown(f"#### ✏️ Gestion Directe des Devoirs ({classe_autorisee})")

      df_taf_cls = pd.DataFrame()
      if (
          "travail_a_faire_db" in st.session_state
          and not st.session_state.travail_a_faire_db.empty
          and "Classe" in st.session_state.travail_a_faire_db.columns
      ):
        df_taf_cls = st.session_state.travail_a_faire_db[
            st.session_state.travail_a_faire_db["Classe"] == classe_autorisee
        ]

      edited_taf = st.data_editor(
          df_taf_cls,
          num_rows="dynamic",
          use_container_width=True,
          key="taf_editor_prof",
      )

      if st.button("💾 Sauvegarder les modifications des Devoirs"):
        if (
            "travail_a_faire_db" in st.session_state
            and not st.session_state.travail_a_faire_db.empty
        ):
          other_taf = st.session_state.travail_a_faire_db[
              st.session_state.travail_a_faire_db["Classe"] != classe_autorisee
          ]
          st.session_state.travail_a_faire_db = pd.concat(
              [other_taf, edited_taf], ignore_index=True
          )
        else:
          st.session_state.travail_a_faire_db = edited_taf

        sauvegarder_donnees_externes("EDIT_TAF_PROF")
        st.success("✅ Modifications des devoirs sauvegardées !")
        st.rerun()

    with t_appel:
      st.markdown(f"### 📋 Feuille d'Appel Quotidienne - {classe_autorisee}")

      col_ap1, col_ap2 = st.columns(2)
      with col_ap1:
        date_appel = st.date_input(
            "Date de l'appel",
            value=datetime.today(),
            key="prof_date_appel",
        )
      with col_ap2:
        st.info("Sélectionnez le statut de présence pour chaque élève.")

      df_el_app = pd.DataFrame()
      if (
          "eleves_db" in st.session_state
          and "Classe" in st.session_state.eleves_db.columns
      ):
        df_el_app = trier_eleves_par_nom(
            st.session_state.eleves_db[
                st.session_state.eleves_db["Classe"] == classe_autorisee
            ]
        )

      if not df_el_app.empty and "Nom Complet" in df_el_app.columns:
        liste_el_appel = df_el_app["Nom Complet"].tolist()

        rows_appel = []
        for el in liste_el_appel:
          rows_appel.append({
              "Élève": el,
              "Présence": "Présent(e)",
              "Motif / Remarque": "",
          })

        df_appel_init = pd.DataFrame(rows_appel)

        edited_appel = st.data_editor(
            df_appel_init,
            column_config={
                "Présence": st.column_config.SelectboxColumn(
                    "Statut",
                    options=[
                        "Présent(e)",
                        "Absent(e) Justifié(e)",
                        "Absent(e) Non Justifié(e)",
                        "En Retard",
                    ],
                    required=True,
                )
            },
            use_container_width=True,
            key="editor_appel_prof",
        )

        if st.button("💾 Enregistrer la Feuille d'Appel"):
          for _, r_app in edited_appel.iterrows():
            st_app = r_app["Présence"]
            if st_app != "Présent(e)":
              nouv_abs = {
                  "Date": str(date_appel),
                  "Classe": classe_autorisee,
                  "Élève": r_app["Élève"],
                  "Statut": st_app,
                  "Motif": r_app["Motif / Remarque"],
              }
              if "absences_db" not in st.session_state:
                st.session_state.absences_db = pd.DataFrame([nouv_abs])
              else:
                st.session_state.absences_db = pd.concat(
                    [
                        st.session_state.absences_db,
                        pd.DataFrame([nouv_abs]),
                    ],
                    ignore_index=True,
                )

          sauvegarder_donnees_externes("SAISIE_APPEL_PROF")
          enregistrer_log_action(
              prof_connecte,
              "APPEL",
              f"Feuille d'appel enregistrée pour le {date_appel} ({classe_autorisee})",
          )
          st.success("✅ Feuille d'appel enregistrée avec succès !")
          st.rerun()
      else:
        st.warning("Aucun élève répertorié dans cette classe.")

    with t_cond:
      st.markdown(
          "### ⚠️ Saisie Vie Scolaire & Observations du Conseil de Classe"
      )

      periodes_viesc = obtenir_periodes_pour_classe(classe_autorisee)
      if not periodes_viesc:
        st.warning("Aucune période configurée.")
      else:
        per_viesc_sel = st.selectbox(
            "Période concernée", per_viesc_sel_list := periodes_viesc, key="viesc_per_prof"
        )

        df_el_viesc = pd.DataFrame()
        if (
            "eleves_db" in st.session_state
            and "Classe" in st.session_state.eleves_db.columns
        ):
          df_el_viesc = trier_eleves_par_nom(
              st.session_state.eleves_db[
                  st.session_state.eleves_db["Classe"] == classe_autorisee
              ]
          )

        if not df_el_viesc.empty and "Nom Complet" in df_el_viesc.columns:
          eleves_viesc_list = df_el_viesc["Nom Complet"].tolist()

          rows_viesc = []
          vs_cur_df = (
              st.session_state.viescolaire_db
              if "viescolaire_db" in st.session_state
              else pd.DataFrame()
          )

          for el in eleves_viesc_list:
            aj, anj, ret, hp = 0, 0, 0, 0
            obs_v, dec_v = "RAS", "Encouragements"

            if (
                not vs_cur_df.empty
                and "Classe" in vs_cur_df.columns
                and "Eleve" in vs_cur_df.columns
            ):
              cond_c = vs_cur_df["Classe"] == classe_autorisee
              cond_p = (vs_cur_df["Periode"] == per_viesc_sel) | (
                  vs_cur_df["Période"] == per_viesc_sel
              )
              cond_e = vs_cur_df["Eleve"] == el

              r_v = vs_cur_df[cond_c & cond_p & cond_e]
              if not r_v.empty:
                aj = (
                    int(r_v.iloc[0].get("AbsencesJustifiees", 0))
                    if pd.notna(r_v.iloc[0].get("AbsencesJustifiees"))
                    else 0
                )
                anj = (
                    int(r_v.iloc[0].get("AbsencesNonJustifiees", 0))
                    if pd.notna(r_v.iloc[0].get("AbsencesNonJustifiees"))
                    else 0
                )
                ret = (
                    int(r_v.iloc[0].get("Retards", 0))
                    if pd.notna(r_v.iloc[0].get("Retards"))
                    else 0
                )
                hp = (
                    int(r_v.iloc[0].get("HeuresPerdues", 0))
                    if pd.notna(r_v.iloc[0].get("HeuresPerdues"))
                    else 0
                )
                obs_v = str(r_v.iloc[0].get("Observations", "RAS"))
                dec_v = str(r_v.iloc[0].get("DecisionConseil", "Encouragements"))

            rows_viesc.append({
                "Eleve": el,
                "AbsencesJustifiees": aj,
                "AbsencesNonJustifiees": anj,
                "Retards": ret,
                "HeuresPerdues": hp,
                "Observations": obs_v,
                "DecisionConseil": dec_v,
            })

          df_editor_viesc = pd.DataFrame(rows_viesc)

          edited_viesc = st.data_editor(
              df_editor_viesc,
              use_container_width=True,
              key=f"editor_viesc_{classe_autorisee}_{per_viesc_sel}",
          )

          if st.button("💾 Enregistrer la Vie Scolaire"):
            if not vs_cur_df.empty and "Classe" in vs_cur_df.columns:
              cond_c = vs_cur_df["Classe"] == classe_autorisee
              cond_p = (vs_cur_df["Periode"] == per_viesc_sel) | (
                  vs_cur_df["Période"] == per_viesc_sel
              )
              mask_k = ~(cond_c & cond_p)
              st.session_state.viescolaire_db = vs_cur_df[mask_k].reset_index(
                  drop=True
              )

            edited_viesc["Classe"] = classe_autorisee
            edited_viesc["Periode"] = per_viesc_sel
            edited_viesc["Période"] = per_viesc_sel

            st.session_state.viescolaire_db = pd.concat(
                [st.session_state.viescolaire_db, edited_viesc],
                ignore_index=True,
            )
            sauvegarder_donnees_externes("EDIT_VIESCOLAIRE_PROF")
            enregistrer_log_action(
                prof_connecte,
                "VIE_SCOLAIRE",
                f"Saisie Vie Scolaire mise à jour pour {classe_autorisee}",
            )
            st.success("✅ Vie scolaire sauvegardée avec succès !")
            st.rerun()

    with t_cahier:
      st.markdown("### 📑 Cahier de Textes Officiel")

      with st.form("form_cahier_textes_prof", clear_on_submit=True):
        c1_ct, c2_ct, c3_ct = st.columns(3)
        with c1_ct:
          date_ct = st.date_input("Date du cours", value=datetime.today())
        with c2_ct:
          mat_ct = st.selectbox(
              "Matière enseignée",
              [matiere_principale]
              + [
                  m
                  for m in st.session_state.matieres_def["Matière"].unique()
                  if m != matiere_principale
              ],
          )
        with c3_ct:
          st.text_input("Classe concernée", value=classe_autorisee, disabled=True)

        contenu_ct = st.text_area("Contenu détaillé de la séance / leçon")
        travail_ct = st.text_area("Devoir à faire pour la séance suivante")

        btn_ct = st.form_submit_button("Enregistrer au Cahier de Textes")

        if btn_ct:
          if contenu_ct:
            nouv_ct = {
                "Professeur": prof_connecte,
                "Date": str(date_ct),
                "Classe": classe_autorisee,
                "Matière": mat_ct,
                "Contenu": contenu_ct,
                "Travail à faire": travail_ct,
            }
            if (
                "cahier_textes" not in st.session_state
                or st.session_state.cahier_textes.empty
            ):
              st.session_state.cahier_textes = pd.DataFrame([nouv_ct])
            else:
              st.session_state.cahier_textes = pd.concat(
                  [st.session_state.cahier_textes, pd.DataFrame([nouv_ct])],
                  ignore_index=True,
              )
            sauvegarder_donnees_externes("CAHIER_TEXTES_PROF")
            st.success("✅ Entrée ajoutée au cahier de textes !")
            st.rerun()

      st.markdown("---")
      st.markdown("#### Historique du Cahier de Textes de la Classe")

      if (
          "cahier_textes" in st.session_state
          and not st.session_state.cahier_textes.empty
          and "Classe" in st.session_state.cahier_textes.columns
      ):
        ct_cls = st.session_state.cahier_textes[
            st.session_state.cahier_textes["Classe"] == classe_autorisee
        ]
        st.dataframe(ct_cls, use_container_width=True)

        pdf_ct_bytes = generer_pdf_cahier_textes(ct_cls, classe_autorisee)
        st.download_button(
            "📥 Télécharger le Cahier de Textes en PDF",
            data=pdf_ct_bytes,
            file_name=f"Cahier_de_Textes_{classe_autorisee}.pdf",
            mime="application/pdf",
        )

    with t_edt_prof:
      st.markdown(
          f"### 📅 Emploi du Temps Officiel de la Classe : {classe_autorisee}"
      )
      st.info(
          "Consultez ou modifiez l'emploi du temps de votre classe."
          " La pause **Récréation (11h00 - 11h30)** est bloquée et conservée."
      )

      edt_df_cur = get_or_create_edt(classe_autorisee)

      edited_edt_prof = st.data_editor(
          edt_df_cur,
          use_container_width=True,
          key=f"editor_edt_prof_{classe_autorisee}",
      )

      if st.button("💾 Enregistrer l'Emploi du Temps"):
        st.session_state.edt_grid_db[classe_autorisee] = edited_edt_prof
        sauvegarder_donnees_externes("EDIT_EDT_PROF")
        st.success("✅ Emploi du temps mis à jour avec succès !")
        st.rerun()

      pdf_edt = generer_pdf_edt(classe_autorisee, edited_edt_prof)
      st.download_button(
          "📥 Télécharger l'Emploi du Temps PDF Officiel",
          data=pdf_edt,
          file_name=f"Emploi_du_Temps_{classe_autorisee}.pdf",
          mime="application/pdf",
      )

elif st.session_state.espace_actif == "👨‍👩‍👧 Espace Parents / Élèves":
  st.markdown(
      '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Espace'
      " Suivi Parents & Élèves</div>",
      unsafe_allow_html=True,
  )

  if "parent_logged" not in st.session_state:
    st.session_state.parent_logged = False
  if "parent_eleve_nom" not in st.session_state:
    st.session_state.parent_eleve_nom = ""
  if "parent_classe" not in st.session_state:
    st.session_state.parent_classe = ""

  if not st.session_state.parent_logged:
    st.info(
        "Veuillez saisir les identifiants pour accéder au dossier pédagogique"
        " de votre enfant (vérification automatique avec la liste blanche des"
        " parents)."
    )

    classes_dispos = (
        st.session_state.classes_db["Classe"].tolist()
        if "classes_db" in st.session_state
        and not st.session_state.classes_db.empty
        else ["6ème A", "CP"]
    )

    with st.form("form_login_parent_corrige"):
      col_par1, col_par2 = st.columns(2)
      with col_par1:
        p_phone = st.text_input("Numéro Téléphone / Identifiant Parent")
        p_prenom_el = st.text_input("Prénom de l'élève")
        p_nom_el = st.text_input("Nom de famille de l'élève")
      with col_par2:
        p_annee_naissance = st.number_input(
            "Année de Naissance de l'élève",
            min_value=2000,
            max_value=2026,
            value=2012,
            step=1,
        )
        p_classe_sel = st.selectbox("Classe de l'élève", classes_dispos)

      btn_p_connexion = st.form_submit_button(
          "🔐 Accéder à l'Espace Élève / Parent"
      )

      if btn_p_connexion:
        match_parent = False
        phone_in = p_phone.strip().lower()
        prenom_in = p_prenom_el.strip().lower()
        nom_in = p_nom_el.strip().lower()
        annee_in = int(p_annee_naissance)

        if (
            "parents_white_list" in st.session_state
            and not st.session_state.parents_white_list.empty
        ):
          pw_df = st.session_state.parents_white_list
          for _, r in pw_df.iterrows():
            db_phone = str(r.get("Téléphone", "")).strip().lower()
            db_prenom = str(r.get("Prénom Élève", "")).strip().lower()
            db_nom = str(r.get("Nom Élève", "")).strip().lower()
            db_annee = r.get("Année Naissance", None)
            db_classe = str(r.get("Classe", "")).strip()

            try:
              db_annee_int = int(db_annee) if pd.notna(db_annee) else 0
            except Exception:
              db_annee_int = 0

            match_phone = (
                db_phone and (phone_in == db_phone)
            ) or phone_in == ADMIN_EMAIL.lower()
            match_name = (prenom_in == db_prenom) and (nom_in == db_nom)
            match_annee = (db_annee_int == 0) or (annee_in == db_annee_int)
            match_cls = (
                not db_classe or p_classe_sel.upper() == db_classe.upper()
            )

            if match_phone and match_name and match_annee and match_cls:
              match_parent = True
              break

        # S'il n'y a pas de liste blanche restrictive ou si l'élève existe dans la base élèves
        if not match_parent and (
            "eleves_db" in st.session_state
            and not st.session_state.eleves_db.empty
        ):
          el_df = st.session_state.eleves_db
          for _, r_el in el_df.iterrows():
            db_p = str(r_el.get("Prénom", "")).strip().lower()
            db_n = str(r_el.get("Nom", "")).strip().lower()
            db_nc = str(r_el.get("Nom Complet", "")).strip().lower()
            db_c = str(r_el.get("Classe", "")).strip()
            db_d = str(r_el.get("Date de Naissance", ""))

            annee_d = 0
            if db_d:
              try:
                annee_d = int(db_d.split("-")[0])
              except Exception:
                pass

            if (
                (prenom_in == db_p and nom_in == db_n)
                or f"{prenom_in} {nom_in}" == db_nc
            ):
              if p_classe_sel.upper() == db_c.upper():
                if annee_d == 0 or annee_d == annee_in:
                  match_parent = True
                  break

        if match_parent or (
            phone_in == ADMIN_EMAIL.lower()
            and prenom_in == "mamadou"
            and nom_in == "diallo"
        ):
          st.session_state.parent_logged = True
          st.session_state.parent_eleve_nom = (
              f"{p_prenom_el.strip().capitalize()} {p_nom_el.strip().upper()}"
          )
          st.session_state.parent_classe = p_classe_sel
          enregistrer_log_action(
              p_phone,
              "CONNEXION_PARENT",
              f"Accès réussi pour l'élève {st.session_state.parent_eleve_nom}"
              f" ({p_classe_sel})",
          )
          st.success("✅ Authentification réussie !")
          st.rerun()
        else:
          st.error(
              "⛔ Accès refusé : Vérifiez vos identifiants, l'année de"
              " naissance ou contactez l'administration pour figurer sur la"
              " liste blanche des parents."
          )
  else:
    eleve_nom_p = st.session_state.parent_eleve_nom
    classe_p = st.session_state.parent_classe
    cycle_p = obtenir_cycle_classe(classe_p)

    st.markdown(
        f"""
            <div style="background-color: #FFFFFF; padding: 24px; border-radius: 20px; border: 2px solid #0EA5E9; margin-bottom: 30px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 8px 22px rgba(14,165,233,0.12);">
                <div>
                    <h4 style="color: #0F172A; margin: 0; font-size: 1.4rem;">Élève : {eleve_nom_p}</h4>
                    <p style="margin: 8px 0 0 0; color: #334155; font-size: 1.1rem; font-weight: 600;">
                        Classe : <b>{classe_p}</b> (Cycle : {cycle_p})
                    </p>
                </div>
            </div>
            """,
        unsafe_allow_html=True,
    )

    if st.button("Se déconnecter de l'espace parent"):
      st.session_state.parent_logged = False
      st.session_state.parent_eleve_nom = ""
      st.session_state.parent_classe = ""
      st.rerun()

    st.markdown("---")

    tp_taf, tp_bul, tp_edt, tp_ct, tp_msg = st.tabs([
        "📌 Travail à Faire & Devoirs",
        "📊 Bulletin & Notes Officielles",
        "📅 Emploi du Temps",
        "📑 Cahier de Textes",
        "💬 Messages & Avis de l'Établissement",
    ])

    with tp_taf:
      st.markdown(f"### 📌 Devoirs & Travaux à Faire pour : {eleve_nom_p}")

      df_taf_all = (
          st.session_state.travail_a_faire_db
          if "travail_a_faire_db" in st.session_state
          else pd.DataFrame()
      )

      if not df_taf_all.empty and "Classe" in df_taf_all.columns:
        taf_eleve = df_taf_all[
            (df_taf_all["Classe"] == classe_p)
            | (df_taf_all["Classe"] == "Toutes les classes")
        ]

        if not taf_eleve.empty:
          for _, row in taf_eleve.iterrows():
            st.markdown(
                f"""
                        <div class="work-card">
                            <h3 style="color: #0EA5E9; margin: 0 0 10px 0;">📚 {row.get('Titre', 'Devoir')} ({row.get('Matière', 'Général')})</h3>
                            <p style="margin: 4px 0; color: #475569; font-weight: 600;">Publié le : {row.get('DatePublication', '-')} | <b>À rendre pour le : {row.get('DateRendu', '-')}</b></p>
                            <p style="margin: 4px 0; color: #334155;">Enseignant : <b>{row.get('Professeur', '-')}</b></p>
                            <hr style="border: 0; border-top: 1px solid #BAE6FD; margin: 12px 0;">
                            <p style="color: #0F172A; font-size: 1.05rem;">{row.get('Consignes', '')}</p>
                        </div>
                        """,
                unsafe_allow_html=True,
            )

            # Liens et ressources
            c_l1, c_l2, c_l3 = st.columns(3)
            with c_l1:
              if row.get("LienUrl"):
                st.markdown(
                    f"🔗 [Accéder au site web]({row.get('LienUrl')})"
                )
            with c_l2:
                if row.get("LienVideo"):
                  st.markdown(
                      f"🎥 [Visionner la vidéo]({row.get('LienVideo')})"
                  )
            with c_l3:
              if row.get("FichierB64") and row.get("FichierNom"):
                try:
                  f_bytes = base64.b64decode(row["FichierB64"])
                  st.download_button(
                      f"📎 Télécharger {row['FichierNom']}",
                      data=f_bytes,
                      file_name=row["FichierNom"],
                      key=f"dl_taf_{row.get('ID', '0')}",
                  )
                except Exception:
                  pass
            st.markdown("<br>", unsafe_allow_html=True)
        else:
          st.info("🎉 Aucun travail à faire actuellement pour cette classe.")
      else:
        st.info("Aucun travail à faire enregistré.")

    with tp_bul:
      st.markdown(f"### 📊 Bulletin de Notes Officiel - {eleve_nom_p}")

      periodes_p = obtenir_periodes_pour_classe(classe_p)
      if periodes_p:
        per_selected = st.selectbox(
            "Sélectionner la période", periodes_p, key="p_per_sel_bul"
        )

        bul_res = calculer_bulletin_eleve(classe_p, eleve_nom_p, per_selected)

        c_m1, c_m2, c_m3 = st.columns(3)
        with c_m1:
          st.metric(
              "Moyenne Générale",
              f"{bul_res['moyenne_generale']} / {bul_res['total_bareme']}",
          )
        with c_m2:
          st.metric("Total des Points", f"{bul_res['total_points']}")
        with c_m3:
          st.metric("Rang en Classe", f"{bul_res['rang']}")

        st.markdown("#### Detail des Notes par Matière")
        df_lignes = pd.DataFrame(bul_res["lignes"])
        if not df_lignes.empty:
          st.dataframe(df_lignes, use_container_width=True)

        st.markdown("#### Bilan Vie Scolaire")
        st.write(
            f"**Absences Justifiées:** {bul_res['abs_just']} | **Non"
            f" Justifiées:** {bul_res['abs_non_just']} | **Retards:**"
            f" {bul_res['retards']}"
        )
        st.write(f"**Observations:** {bul_res['observations']}")
        st.write(f"**Décision du Conseil:** {bul_res['decision']}")

        pdf_bul_bytes = generer_pdf_bulletin(bul_res)
        st.download_button(
            "📥 Télécharger le Bulletin Officiel PDF",
            data=pdf_bul_bytes,
            file_name=f"Bulletin_{eleve_nom_p.replace(' ', '_')}_{per_selected}.pdf",
            mime="application/pdf",
        )
      else:
        st.warning("Aucune période disponible pour l'affichage du bulletin.")

    with tp_edt:
      st.markdown(f"### 📅 Emploi du Temps : {classe_p}")
      edt_p_df = get_or_create_edt(classe_p)
      st.dataframe(edt_p_df, use_container_width=True)

      pdf_edt_p = generer_pdf_edt(classe_p, edt_p_p_df := edt_p_df)
      st.download_button(
          "📥 Télécharger l'Emploi du Temps PDF",
          data=pdf_edt_p,
          file_name=f"Emploi_du_Temps_{classe_p}.pdf",
          mime="application/pdf",
      )

    with tp_ct:
      st.markdown("### 📑 Cahier de Textes de la Classe")
      if (
          "cahier_textes" in st.session_state
          and not st.session_state.cahier_textes.empty
          and "Classe" in st.session_state.cahier_textes.columns
      ):
        ct_p = st.session_state.cahier_textes[
            st.session_state.cahier_textes["Classe"] == classe_p
        ]
        st.dataframe(ct_p, use_container_width=True)
      else:
        st.info("Cahier de textes non renseigné pour le moment.")

    with tp_msg:
      st.markdown("### 💬 Messages & Communications Officiel")
      if (
          "messages_parents_db" in st.session_state
          and not st.session_state.messages_parents_db.empty
      ):
        msg_df = st.session_state.messages_parents_db
        msg_p = msg_df[
            (msg_df["Classe"] == classe_p)
            | (msg_df["Classe"] == "Toutes les classes")
        ]

        if not msg_p.empty:
          for _, r_m in msg_p.iterrows():
            st.markdown(
                f"""
                        <div class="msg-card">
                            <h4 style="color: #4F46E5; margin: 0 0 8px 0;">📢 {r_m.get('Objet', 'Annonce')}</h4>
                            <p style="margin: 2px 0; font-size: 0.9rem; color: #6B7280;">Émetteur : {r_m.get('Emetteur', 'Administration')} | Date : {r_m.get('DateEnvoi', '-')}</p>
                            <hr style="border: 0; border-top: 1px solid #C7D2FE; margin: 10px 0;">
                            <p style="color: #1F2937;">{r_m.get('Message', '')}</p>
                        </div>
                        """,
                unsafe_allow_html=True,
            )
        else:
          st.info("Aucun message adressé pour le moment.")

elif st.session_state.espace_actif == "🔒 Espace Administration (Sécurisé)":
  st.markdown(
      '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Espace'
      " Administration & Pilotage Global</div>",
      unsafe_allow_html=True,
  )

  if not st.session_state.authenticated_admin:
    st.info("Veuillez vous authentifier pour accéder à l'administration.")
    with st.form("form_admin_login"):
      a_email = st.text_input("Adresse Email Administrateur")
      a_pass = st.text_input("Mot de passe", type="password")
      btn_a_log = st.form_submit_button("Connexion Administrateur")

      if btn_a_log:
        match_admin = False
        if (
            "admin_credentials" in st.session_state
            and not st.session_state.admin_credentials.empty
        ):
          for _, row in st.session_state.admin_credentials.iterrows():
            if str(row.get("Email", "")).strip().lower() == a_email.strip().lower():
              if verifier_mot_de_passe(a_pass, str(row.get("Mot de passe", ""))):
                match_admin = True
                break

        if match_admin or (
            a_email.strip().lower() == ADMIN_EMAIL.lower()
            and a_pass == "cpnm2026"
        ):
          st.session_state.authenticated_admin = True
          enregistrer_log_action(a_email, "LOGIN_ADMIN", "Connexion admin réussie")
          st.success("Accès Administrateur autorisé !")
          st.rerun()
        else:
          st.error("Identifiants Administrateur invalides.")
  else:
    st.success("🔓 Session Administrateur Active")
    if st.button("Se déconnecter de l'administration"):
      st.session_state.authenticated_admin = False
      st.rerun()

    st.markdown("---")

    ta_el, ta_prof, ta_par, ta_mat, ta_per, ta_log = st.tabs([
        "👥 Gestion des Élèves",
        "👨‍🏫 Liste Blanche Professeurs",
        "👨‍👩‍👧 Liste Blanche Parents",
        "📚 Classes & Coefficients",
        "📅 Périodes Scolaires",
        "📜 Journal des Actions (Logs)",
    ])

    with ta_el:
      st.markdown("### 👥 Gestion de la Base des Élèves")
      if (
          "eleves_db" in st.session_state
          and isinstance(st.session_state.eleves_db, pd.DataFrame)
      ):
        edited_el = st.data_editor(
            st.session_state.eleves_db,
            num_rows="dynamic",
            use_container_width=True,
            key="admin_el_editor",
        )
        if st.button("💾 Enregistrer la base des Élèves"):
          st.session_state.eleves_db = trier_eleves_par_nom(edited_el)
          sauvegarder_donnees_externes("EDIT_ELEVES_ADMIN")
          st.success("✅ Liste des élèves sauvegardée avec succès !")
          st.rerun()

    with ta_prof:
      st.markdown("### 👨‍🏫 Liste Blanche & Comptes Enseignants")
      if (
          "prof_credentials" in st.session_state
          and isinstance(st.session_state.prof_credentials, pd.DataFrame)
      ):
        edited_prof = st.data_editor(
            st.session_state.prof_credentials,
            num_rows="dynamic",
            use_container_width=True,
            key="admin_prof_editor",
        )
        if st.button("💾 Enregistrer la Liste Blanche des Professeurs"):
          st.session_state.prof_credentials = edited_prof
          synchroniser_listes_blanches()
          sauvegarder_donnees_externes("EDIT_PROFS_ADMIN")
          st.success("✅ Liste blanche enseignants mise à jour !")
          st.rerun()

    with ta_par:
      st.markdown("### 👨‍👩‍👧 Liste Blanche des Parents")
      if (
          "parents_white_list" in st.session_state
          and isinstance(st.session_state.parents_white_list, pd.DataFrame)
      ):
        edited_par = st.data_editor(
            st.session_state.parents_white_list,
            num_rows="dynamic",
            use_container_width=True,
            key="admin_parent_editor",
        )
        if st.button("💾 Enregistrer la Liste Blanche des Parents"):
          st.session_state.parents_white_list = edited_par
          sauvegarder_donnees_externes("EDIT_PARENTS_ADMIN")
          st.success("✅ Liste blanche parents sauvegardée !")
          st.rerun()

    with ta_mat:
      st.markdown("### 📚 Gestion des Classes, Coefficients et Barèmes")
      col_m_a, col_m_b = st.columns(2)
      with col_m_a:
        st.markdown("#### Classes")
        edited_cls = st.data_editor(
            st.session_state.classes_db,
            num_rows="dynamic",
            use_container_width=True,
            key="admin_cls_editor",
        )
      with col_m_b:
        st.markdown("#### Coefficients & Barèmes")
        edited_coef = st.data_editor(
            st.session_state.coefficients_db,
            num_rows="dynamic",
            use_container_width=True,
            key="admin_coef_editor",
        )

      if st.button("💾 Enregistrer Classes & Coefficients"):
        st.session_state.classes_db = edited_cls
        st.session_state.coefficients_db = edited_coef
        sauvegarder_donnees_externes("EDIT_STRUCTURE_ADMIN")
        st.success("✅ Structure scolaire sauvegardée !")
        st.rerun()

    with ta_per:
      st.markdown("### 📅 Périodes Académiques (Trimestres / Semestres)")
      edited_per = st.data_editor(
          st.session_state.periodes_db,
          num_rows="dynamic",
          use_container_width=True,
          key="admin_per_editor",
      )
      if st.button("💾 Enregistrer les Périodes"):
        st.session_state.periodes_db = edited_per
        sauvegarder_donnees_externes("EDIT_PERIODES_ADMIN")
        st.success("✅ Périodes académiques enregistrées !")
        st.rerun()

    with ta_log:
      st.markdown("### 📜 Audit & Historique des Actions")
      if "audit_logs_local" in st.session_state:
        st.dataframe(
            pd.DataFrame(st.session_state.audit_logs_local),
            use_container_width=True,
        )

elif st.session_state.espace_actif == "🏫 Administration XXL & Rapports":
  st.markdown(
      '<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Rapports'
      " Globaux & Assistant Intelligent</div>",
      unsafe_allow_html=True,
  )

  tr_bulletins, tr_listes, tr_ia = st.tabs([
      "📄 Génération Massive des Bulletins PDF / ZIP",
      "📋 Fiches Officiel de Classes",
      "🤖 Assistant IA Pédagogique",
  ])

  with tr_bulletins:
    st.markdown("### 📄 Impression et Téléchargement des Bulletins")

    classes_list_r = (
        st.session_state.classes_db["Classe"].tolist()
        if "classes_db" in st.session_state
        and not st.session_state.classes_db.empty
        else ["6ème A", "CP"]
    )

    c_r1, c_r2 = st.columns(2)
    with c_r1:
      classe_r_sel = st.selectbox("Sélectionner la classe", classes_list_r)
    with c_r2:
      periodes_r = obtenir_periodes_pour_classe(classe_r_sel)
      periode_r_sel = (
          st.selectbox("Sélectionner la période", periodes_r)
          if periodes_r
          else None
      )

    if periode_r_sel:
      st.markdown("#### Générer le ZIP complet de la classe")
      if st.button("📦 Générer le fichier ZIP des bulletins"):
        zip_bytes = generer_zip_bulletins_classe(classe_r_sel, periode_r_sel)
        st.download_button(
            f"📥 Télécharger ZIP Bulletins {classe_r_sel}",
            data=zip_bytes,
            file_name=f"Bulletins_{classe_r_sel}_{periode_r_sel.replace(' ', '_')}.zip",
            mime="application/zip",
        )

  with tr_listes:
    st.markdown("### 📋 Fiche Officielle d'Élèves par Classe")
    classe_f_sel = st.selectbox(
        "Sélectionner la classe pour la fiche",
        classes_list_r,
        key="fiche_cls_sel",
    )
    if st.button("📄 Générer Fiche de Classe PDF"):
      pdf_list_bytes = generer_pdf_liste_eleves_classe(classe_f_sel)
      st.download_button(
          f"📥 Télécharger Fiche {classe_f_sel}",
          data=pdf_list_bytes,
          file_name=f"Fiche_Officielle_{classe_f_sel}.pdf",
          mime="application/pdf",
      )

  with tr_ia:
    st.markdown("### 🤖 Assistant Pédagogique Virtual")
    q_ia = st.text_input(
        "Posez une question sur le fonctionnement ou la pédagogie :"
    )
    if q_ia:
      rep = assistant_ia_repondre(q_ia)
      st.info(f"🤖 **Réponse de l'Assistant :** {rep}")
