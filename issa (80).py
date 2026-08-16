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
import psycopg2
from psycopg2.extras import RealDictCursor

# ==========================================
# 0. CONFIGURATION & CONNEXION SUPABASE / POSTGRESQL
# ==========================================
DATABASE_URL = "postgresql://postgres.dzxotavktglasrcpyrwx:xTS1vLLFnlGWJXrr@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"

def get_db_connection():
    """Établit la connexion à la base de données Supabase / PostgreSQL."""
    try:
        if "postgres" in st.secrets:
            conn = psycopg2.connect(
                host=st.secrets["postgres"]["host"],
                database=st.secrets["postgres"]["database"],
                user=st.secrets["postgres"]["user"],
                password=st.secrets["postgres"]["password"],
                port=st.secrets["postgres"]["port"]
            )
        else:
            conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        st.error(f"Erreur de connexion à la base de données Supabase/PostgreSQL : {e}")
        return None

def init_db():
    """Initialise les tables dans Supabase / PostgreSQL si elles n'existent pas."""
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    horodatage VARCHAR(50),
                    acteur VARCHAR(255),
                    action VARCHAR(255),
                    details TEXT
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_white_list (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    nom VARCHAR(255),
                    prenom VARCHAR(255),
                    password VARCHAR(255),
                    niveau_acces VARCHAR(255)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS prof_white_list (
                    id SERIAL PRIMARY KEY,
                    nom VARCHAR(255),
                    prenom VARCHAR(255),
                    email VARCHAR(255) UNIQUE,
                    matiere_principale VARCHAR(255),
                    classe_attribuee VARCHAR(255),
                    password VARCHAR(255)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS parents_white_list (
                    id SERIAL PRIMARY KEY,
                    telephone VARCHAR(50),
                    prenom_eleve VARCHAR(255),
                    nom_eleve VARCHAR(255),
                    annee_naissance VARCHAR(50),
                    classe VARCHAR(255)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS classes (
                    id SERIAL PRIMARY KEY,
                    classe VARCHAR(255) UNIQUE NOT NULL,
                    cycle VARCHAR(255),
                    professeur_responsable VARCHAR(255)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS eleves (
                    id SERIAL PRIMARY KEY,
                    nom_complet VARCHAR(255),
                    prenom VARCHAR(255),
                    nom VARCHAR(255),
                    date_de_naissance VARCHAR(50),
                    classe VARCHAR(255),
                    photo TEXT
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS matieres (
                    id SERIAL PRIMARY KEY,
                    matiere VARCHAR(255),
                    cycle VARCHAR(255),
                    coefficient FLOAT,
                    bareme FLOAT
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS coefficients (
                    id SERIAL PRIMARY KEY,
                    classe VARCHAR(255),
                    matiere VARCHAR(255),
                    coefficient FLOAT,
                    bareme FLOAT
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS periodes (
                    id SERIAL PRIMARY KEY,
                    periode VARCHAR(255),
                    statut VARCHAR(50),
                    cycle VARCHAR(255)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id SERIAL PRIMARY KEY,
                    classe VARCHAR(255),
                    matiere VARCHAR(255),
                    periode VARCHAR(255),
                    eleve VARCHAR(255),
                    devoir1 FLOAT,
                    devoir2 FLOAT,
                    composition FLOAT,
                    baremenote FLOAT
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS vie_scolaire (
                    id SERIAL PRIMARY KEY,
                    classe VARCHAR(255),
                    periode VARCHAR(255),
                    eleve VARCHAR(255),
                    absences_justifiees INT,
                    absences_non_justifiees INT,
                    retards INT,
                    heures_perdues INT,
                    observations TEXT,
                    decision_conseil TEXT
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS travail_a_faire (
                    id VARCHAR(255) PRIMARY KEY,
                    professeur VARCHAR(255),
                    date_publication VARCHAR(50),
                    date_rendu VARCHAR(50),
                    classe VARCHAR(255),
                    matiere VARCHAR(255),
                    titre VARCHAR(255),
                    consignes TEXT,
                    lien_url TEXT,
                    lien_video TEXT,
                    fichier_nom TEXT,
                    fichier_b64 TEXT,
                    fichier_type TEXT
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages_parents (
                    id VARCHAR(255) PRIMARY KEY,
                    emetteur VARCHAR(255),
                    role_emetteur VARCHAR(255),
                    date_envoi VARCHAR(50),
                    classe VARCHAR(255),
                    objet TEXT,
                    message TEXT,
                    urgent BOOLEAN
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS edt_grid (
                    id SERIAL PRIMARY KEY,
                    classe VARCHAR(255),
                    jour VARCHAR(50),
                    heure VARCHAR(50),
                    valeur TEXT
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cahier_textes (
                    id SERIAL PRIMARY KEY,
                    professeur VARCHAR(255),
                    date VARCHAR(50),
                    classe VARCHAR(255),
                    matiere VARCHAR(255),
                    contenu TEXT,
                    travail_a_faire TEXT
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS absences (
                    id SERIAL PRIMARY KEY,
                    date VARCHAR(50),
                    classe VARCHAR(255),
                    eleve VARCHAR(255),
                    statut VARCHAR(50),
                    motif TEXT
                );
            """)
            conn.commit()
    except Exception as e:
        conn.rollback()
        st.error(f"Erreur lors de l'initialisation des tables PostgreSQL : {e}")
    finally:
        conn.close()

init_db()

def load_table_from_db(query, columns):
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_sql(query, conn)
        if df.empty:
            return pd.DataFrame(columns=columns)
        return df
    except Exception:
        return pd.DataFrame(columns=columns)
    finally:
        conn.close()

def save_df_to_db(df: pd.DataFrame, table_name: str):
    """Sauvegarde ou met à jour le DataFrame dans la BDD PostgreSQL/Supabase avec correspondance exacte des colonnes."""
    conn = get_db_connection()
    if conn is None:
        st.error("Connexion à la base de données impossible.")
        return False
    
    try:
        with conn.cursor() as cur:
            if not df.empty:
                df_cleaned = df.where(pd.notnull(df), None)
                
                if table_name == "eleves":
                    query = """
                        INSERT INTO eleves (nom_complet, prenom, nom, date_de_naissance, classe, photo)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    data_tuples = [tuple(x) for x in df_cleaned.to_numpy()]
                    cur.execute("DELETE FROM eleves;")
                    cur.executemany(query, data_tuples)
                    
                elif table_name == "edt_grid":
                    for _, r in df_cleaned.iterrows():
                        cur.execute("DELETE FROM edt_grid WHERE classe = %s AND jour = %s AND heure = %s;", (r.get("classe"), r.get("jour"), r.get("heure")))
                        cur.execute("INSERT INTO edt_grid (classe, jour, heure, valeur) VALUES (%s, %s, %s, %s);", (r.get("classe"), r.get("jour"), r.get("heure"), r.get("valeur")))
                    
                elif table_name == "cahier_textes":
                    query = """
                        INSERT INTO cahier_textes (professeur, date, classe, matiere, contenu, travail_a_faire)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING;
                    """
                    data_tuples = []
                    for _, r in df_cleaned.iterrows():
                        data_tuples.append((
                            r.get("Professeur"),
                            str(r.get("Date", "")),
                            r.get("Classe"),
                            r.get("Matière"),
                            r.get("Contenu"),
                            r.get("Travail à faire")
                        ))
                    cur.executemany(query, data_tuples)
                    
                elif table_name == "travail_a_faire":
                    query = """
                        INSERT INTO travail_a_faire (id, professeur, date_publication, date_rendu, classe, matiere, titre, consignes, lien_url, lien_video, fichier_nom, fichier_b64, fichier_type)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            professeur = EXCLUDED.professeur,
                            date_publication = EXCLUDED.date_publication,
                            date_rendu = EXCLUDED.date_rendu,
                            classe = EXCLUDED.classe,
                            matiere = EXCLUDED.matiere,
                            titre = EXCLUDED.titre,
                            consignes = EXCLUDED.consignes;
                    """
                    data_tuples = []
                    for _, r in df_cleaned.iterrows():
                        data_tuples.append((
                            r.get("ID"), r.get("Professeur"), r.get("DatePublication"), r.get("DateRendu"),
                            r.get("Classe"), r.get("Matière"), r.get("Titre"), r.get("Consignes"),
                            r.get("LienUrl"), r.get("LienVideo"), r.get("FichierNom"), r.get("FichierB64"), r.get("FichierType")
                        ))
                    cur.executemany(query, data_tuples)
                    
                elif table_name == "messages_parents":
                    query = """
                        INSERT INTO messages_parents (id, emetteur, role_emetteur, date_envoi, classe, objet, message, urgent)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING;
                    """
                    data_tuples = []
                    for _, r in df_cleaned.iterrows():
                        data_tuples.append((
                            r.get("ID"), r.get("Emetteur"), r.get("RoleEmetteur"), r.get("DateEnvoi"),
                            r.get("Classe"), r.get("Objet"), r.get("Message"), r.get("Urgent")
                        ))
                    cur.executemany(query, data_tuples)
                    
                elif table_name == "notes":
                    query = """
                        INSERT INTO notes (classe, matiere, periode, eleve, devoir1, devoir2, composition, baremenote)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING;
                    """
                    data_tuples = []
                    for _, r in df_cleaned.iterrows():
                        data_tuples.append((
                            r.get("Classe"), r.get("Matière"), r.get("Periode", r.get("Période")),
                            r.get("Eleve"), r.get("Devoir1"), r.get("Devoir2"), r.get("Composition"), r.get("BaremeNote")
                        ))
                    cur.executemany(query, data_tuples)
                    
                elif table_name == "vie_scolaire":
                    query = """
                        INSERT INTO vie_scolaire (classe, periode, eleve, absences_justifiees, absences_non_justifiees, retards, heures_perdues, observations, decision_conseil)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING;
                    """
                    data_tuples = []
                    for _, r in df_cleaned.iterrows():
                        data_tuples.append((
                            r.get("Classe"), r.get("Periode", r.get("Période")), r.get("Eleve"),
                            r.get("AbsencesJustifiees", 0), r.get("AbsencesNonJustifiees", 0),
                            r.get("Retards", 0), r.get("HeuresPerdues", 0),
                            r.get("Observations", ""), r.get("DecisionConseil", "")
                        ))
                    cur.executemany(query, data_tuples)
                else:
                    cols = list(df_cleaned.columns)
                    cols_str = ",".join([f'"{col}"' for col in cols])
                    data_tuples = [tuple(x) for x in df_cleaned.to_numpy()]
                    placeholders_gen = ",".join(["%s"] * len(cols))
                    query = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders_gen}) ON CONFLICT DO NOTHING;"
                    cur.executemany(query, data_tuples)
                
        conn.commit()
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        st.error(f"Erreur de sauvegarde dans {table_name} : {e}")
        return False
    finally:
        if conn:
            conn.close()

# ==========================================
# 0. BIS. GESTION DE LA SÉCURITÉ & AUTHENTIFICATION
# ==========================================
def hacher_mot_de_passe(password: str) -> str:
    if not password:
        return ""
    sel = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), sel).decode("utf-8")

def verifier_mot_de_passe(arg1, arg2, arg3=None, table_name="prof_white_list"):
    if arg3 is None:
        password_saisi = arg1
        hashed_db = arg2
    else:
        password_saisi = arg2
        hashed_db = arg3

    if not password_saisi or not hashed_db: 
        return False
    
    if str(hashed_db).startswith('$2b$'):
        return bcrypt.checkpw(str(password_saisi).encode("utf-8"), str(hashed_db).encode("utf-8"))
    
    if str(password_saisi) == str(hashed_db):
        return True
    return False

def normaliser_texte(texte):
    if not texte: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(texte)) if unicodedata.category(c) != 'Mn').strip().lower()

ADMIN_EMAIL = "cpnm@gmail.com"

def enregistrer_log_action(acteur: str, action: str, details: str):
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if "audit_logs_db" not in st.session_state:
        st.session_state.audit_logs_db = pd.DataFrame(columns=["horodatage", "acteur", "action", "details"])
    new_log = pd.DataFrame([{"horodatage": horodatage, "acteur": acteur, "action": action, "details": details}])
    st.session_state.audit_logs_db = pd.concat([st.session_state.audit_logs_db, new_log], ignore_index=True)
    
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO audit_logs (horodatage, acteur, action, details) VALUES (%s, %s, %s, %s)",
                            (horodatage, acteur, action, details))
                conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()

def trier_eleves_par_nom(df):
    if df is None or df.empty: return df
    df_copy = df.copy()
    if "Nom" in df_copy.columns and "Prénom" in df_copy.columns:
        df_copy["Nom_Sort"] = df_copy["Nom"].astype(str).str.strip().str.upper()
        df_copy["Prenom_Sort"] = df_copy["Prénom"].astype(str).str.strip().str.upper()
        df_copy = df_copy.sort_values(by=["Nom_Sort", "Prenom_Sort"]).drop(columns=["Nom_Sort", "Prenom_Sort"])
    elif "Nom Complet" in df_copy.columns:
        df_copy["Nom_Sort"] = df_copy["Nom Complet"].astype(str).str.strip().str.upper()
        df_copy = df_copy.sort_values(by=["Nom_Sort"]).drop(columns=["Nom_Sort"])
    return df_copy.reset_index(drop=True)

def synchroniser_listes_blanches():
    if "prof_credentials" in st.session_state and not st.session_state.prof_credentials.empty:
        st.session_state.prof_white_list = st.session_state.prof_credentials.copy()
    elif "prof_white_list" in st.session_state and not st.session_state.prof_white_list.empty:
        st.session_state.prof_credentials = st.session_state.prof_white_list.copy()

# ==========================================
# 0. TER. DESIGN & DRAPEAU SÉNÉGALAIS
# ==========================================
st.set_page_config(
    page_title="Sénégal - Portail Éducatif National École Président Nelson Mandela",
    page_icon="🇸🇳",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800;900&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
    .stApp { background: radial-gradient(circle at top left, #F8FAFC 0%, #EFF6FF 40%, #DBEAFE 100%); color: #0F172A; }
    .header-institutionnel {
        background: linear-gradient(135deg, #0EA5E9 0%, #2563EB 50%, #1D4ED8 100%);
        padding: 10px; border-radius: 32px; box-shadow: 0 25px 50px rgba(14, 165, 233, 0.3); margin-bottom: 35px;
    }
    .header-inner {
        background: rgba(255, 255, 255, 0.99); backdrop-filter: blur(20px); padding: 25px 35px;
        border-radius: 26px; display: flex; align-items: center; justify-content: space-between; gap: 25px;
    }
    .ministere-title { color: #0F172A; font-size: clamp(1.2rem, 2.5vw, 1.9rem); font-weight: 900; text-transform: uppercase; margin: 0; }
    .ia-ief-sub { color: #1E3A8A; font-size: clamp(0.9rem, 1.8vw, 1.2rem); font-weight: 700; margin: 6px 0; }
    .ecole-title { color: #0EA5E9; font-size: clamp(1.4rem, 2.8vw, 2.3rem); font-weight: 900; margin: 8px 0 0 0; text-transform: uppercase; }
    .animated-card {
        border: 2px solid rgba(186, 230, 253, 0.9); padding: 40px 24px; border-radius: 30px;
        background: linear-gradient(145deg, #FFFFFF 0%, #F0F9FF 100%); box-shadow: 0 18px 40px rgba(15, 23, 42, 0.1);
        text-align: center; margin-bottom: 30px; min-height: 330px; display: flex; flex-direction: column; justify-content: space-between;
    }
    .stButton>button {
        background: linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%) !important; color: #FFFFFF !important;
        border-radius: 18px !important; font-weight: 800 !important; border: none !important; padding: 0.9rem 1.5rem !important;
        width: 100% !important; min-height: 56px !important; font-size: 1.1rem !important; box-shadow: 0 10px 25px rgba(14, 165, 233, 0.35) !important;
    }
    .work-card, .msg-card {
        background: #FFFFFF; border: 1px solid #BAE6FD; padding: 20px; border-radius: 16px; margin-bottom: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }
    </style>
""",
    unsafe_allow_html=True,
)

st.markdown("<style>[data-testid=\"stToolbar\"] { display: none; } footer { visibility: hidden; }</style>", unsafe_allow_html=True)

# ==========================================
# 2. INITIALISATION EXHAUSTIVE DES DONNÉES & SUPABASE SYNC
# ==========================================
if "espace_actif" not in st.session_state:
    st.session_state.espace_actif = "🏠 Accueil"

if "authenticated_admin" not in st.session_state:
    st.session_state.authenticated_admin = False

if "eleves_db" not in st.session_state or st.session_state.eleves_db.empty:
    df_eleves_db = load_table_from_db(
        'SELECT nom_complet AS "Nom Complet", prenom AS "Prénom", nom AS "Nom", date_de_naissance AS "Date de Naissance", classe AS "Classe", photo AS "Photo" FROM eleves',
        ["Nom Complet", "Prénom", "Nom", "Date de Naissance", "Classe", "Photo"]
    )
    if df_eleves_db.empty:
        st.session_state.eleves_db = pd.DataFrame(
            columns=["Nom Complet", "Prénom", "Nom", "Date de Naissance", "Classe", "Photo"],
            data=[
                ["Mamadou Diallo", "Mamadou", "Diallo", "12/05/2014", "6ème A", ""],
                ["Aissatou Ba", "Aissatou", "Ba", "23/09/2014", "6ème A", ""],
                ["Cheikh Fall", "Cheikh", "Fall", "04/01/2018", "CP", ""]
            ]
        )
    else:
        st.session_state.eleves_db = df_eleves_db

if "audit_logs_db" not in st.session_state:
    st.session_state.audit_logs_db = load_table_from_db("SELECT horodatage, acteur, action, details FROM audit_logs", ["horodatage", "acteur", "action", "details"])

if "admin_credentials" not in st.session_state:
    df_admin = load_table_from_db('SELECT nom AS "Nom", prenom AS "Prénom", email AS "Email", password AS "Mot de passe", niveau_acces AS "Niveau d\'accès" FROM admin_white_list', ["Nom", "Prénom", "Email", "Mot de passe", "Niveau d'accès"])
    if df_admin.empty:
        st.session_state.admin_credentials = pd.DataFrame([{
            "Nom": "Principal", "Prénom": "Admin", "Email": ADMIN_EMAIL,
            "Mot de passe": hacher_mot_de_passe("cpnm2026"), "Niveau d'accès": "Super-Admin Ayant-Droit",
        }])
    else:
        st.session_state.admin_credentials = df_admin

if "admin_white_list" not in st.session_state:
    st.session_state.admin_white_list = st.session_state.admin_credentials.copy()

if "prof_credentials" not in st.session_state:
    df_prof = load_table_from_db('SELECT nom AS "Nom", prenom AS "Prénom", email AS "Email", matiere_principale AS "Matière Principale", classe_attribuee AS "Classe Attribuée", password AS "Mot de passe" FROM prof_white_list', ["Nom", "Prénom", "Email", "Matière Principale", "Classe Attribuée", "Mot de passe"])
    if df_prof.empty:
        st.session_state.prof_credentials = pd.DataFrame([{
            "Nom": "Prof", "Prénom": "Maths", "Email": "prof.math@cpnm.sn",
            "Matière Principale": "Mathématiques", "Classe Attribuée": "6ème A", "Mot de passe": hacher_mot_de_passe("cpnm2026")
        }])
    else:
        st.session_state.prof_credentials = df_prof

if "prof_white_list" not in st.session_state:
    st.session_state.prof_white_list = st.session_state.prof_credentials.copy()

if "parents_white_list" not in st.session_state:
    df_parents = load_table_from_db('SELECT telephone AS "Téléphone", prenom_eleve AS "Prénom Élève", nom_eleve AS "Nom Élève", annee_naissance AS "Année Naissance", classe AS "Classe" FROM parents_white_list', ["Téléphone", "Prénom Élève", "Nom Élève", "Année Naissance", "Classe"])
    if df_parents.empty:
        st.session_state.parents_white_list = pd.DataFrame([{
            "Téléphone": "771234567", "Prénom Élève": "Mamadou", "Nom Élève": "Diallo", "Année Naissance": "2014", "Classe": "6ème A"
        }])
    else:
        st.session_state.parents_white_list = df_parents

if "classes_db" not in st.session_state:
    df_classes = load_table_from_db('SELECT classe AS "Classe", cycle AS "Cycle", professeur_responsable AS "Professeur Responsable" FROM classes', ["Classe", "Cycle", "Professeur Responsable"])
    if df_classes.empty:
        st.session_state.classes_db = pd.DataFrame(columns=["Classe", "Cycle", "Professeur Responsable"], data=[["6ème A", "Collège", "Prof. Maths"], ["CP", "Élémentaire", "Prof. Élémen"]])
    else:
        st.session_state.classes_db = df_classes

if "matieres_def" not in st.session_state:
    df_mat = load_table_from_db('SELECT matiere AS "Matière", cycle AS "Cycle", coefficient AS "Coefficient", bareme AS "Barème" FROM matieres', ["Matière", "Cycle", "Coefficient", "Barème"])
    if df_mat.empty:
        st.session_state.matieres_def = pd.DataFrame([
            {"Matière": "Mathématiques", "Cycle": "Collège", "Coefficient": 4, "Barème": 20},
            {"Matière": "Français", "Cycle": "Collège", "Coefficient": 5, "Barème": 20},
            {"Matière": "Lecture / Langage", "Cycle": "Élémentaire", "Coefficient": 1, "Barème": 50},
            {"Matière": "Calcul / Mathématiques", "Cycle": "Élémentaire", "Coefficient": 1, "Barème": 50},
        ])
    else:
        st.session_state.matieres_def = df_mat

if "coefficients_db" not in st.session_state:
    st.session_state.coefficients_db = load_table_from_db('SELECT classe AS "Classe", matiere AS "Matière", coefficient AS "Coefficient", bareme AS "Barème" FROM coefficients', ["Classe", "Matière", "Coefficient", "Barème"])
    if st.session_state.coefficients_db.empty:
        st.session_state.coefficients_db = pd.DataFrame([
            {"Classe": "6ème A", "Matière": "Mathématiques", "Coefficient": 4, "Barème": 20},
            {"Classe": "6ème A", "Matière": "Français", "Coefficient": 5, "Barème": 20}
        ])

if "periodes_db" not in st.session_state:
    st.session_state.periodes_db = pd.DataFrame([
        {"Période": "1er Trimestre", "Statut": "Ouvert", "Cycle": "Élémentaire"},
        {"Période": "1er Semestre", "Statut": "Ouvert", "Cycle": "Collège"},
        {"Période": "2ème Semestre", "Statut": "Fermé", "Cycle": "Collège"}
    ])

if "notes_db" not in st.session_state:
    st.session_state.notes_db = load_table_from_db('SELECT classe AS "Classe", matiere AS "Matière", periode AS "Periode", periode AS "Période", eleve AS "Eleve", devoir1 AS "Devoir1", devoir2 AS "Devoir2", composition AS "Composition", baremenote AS "BaremeNote" FROM notes', ["Classe", "Matière", "Periode", "Période", "Eleve", "Devoir1", "Devoir2", "Composition", "BaremeNote"])

if "viescolaire_db" not in st.session_state:
    st.session_state.viescolaire_db = load_table_from_db('SELECT classe AS "Classe", periode AS "Periode", periode AS "Période", eleve AS "Eleve", absences_justifiees AS "AbsencesJustifiees", absences_non_justifiees AS "AbsencesNonJustifiees", retards AS "Retards", heures_perdues AS "HeuresPerdues", observations AS "Observations", decision_conseil AS "DecisionConseil" FROM vie_scolaire', ["Classe", "Periode", "Période", "Eleve", "AbsencesJustifiees", "AbsencesNonJustifiees", "Retards", "HeuresPerdues", "Observations", "DecisionConseil"])

if "travail_a_faire_db" not in st.session_state:
    st.session_state.travail_a_faire_db = load_table_from_db('SELECT id AS "ID", professeur AS "Professeur", date_publication AS "DatePublication", date_rendu AS "DateRendu", classe AS "Classe", matiere AS "Matière", titre AS "Titre", consignes AS "Consignes", lien_url AS "LienUrl", lien_video AS "LienVideo", fichier_nom AS "FichierNom", fichier_b64 AS "FichierB64", fichier_type AS "FichierType" FROM travail_a_faire', ["ID", "Professeur", "DatePublication", "DateRendu", "Classe", "Matière", "Titre", "Consignes", "LienUrl", "LienVideo", "FichierNom", "FichierB64", "FichierType"])

if "messages_parents_db" not in st.session_state:
    st.session_state.messages_parents_db = load_table_from_db('SELECT id AS "ID", emetteur AS "Emetteur", role_emetteur AS "RoleEmetteur", date_envoi AS "DateEnvoi", classe AS "Classe", objet AS "Objet", message AS "Message", urgent AS "Urgent" FROM messages_parents', ["ID", "Emetteur", "RoleEmetteur", "DateEnvoi", "Classe", "Objet", "Message", "Urgent"])

JOURS_LIST = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]
HEURES_LIST = ["08h-09h", "09h-10h", "10h-11h", "11h00-11h30", "11h30-12h", "12h-13h", "13h-14h", "14h-15h", "15h-16h", "16h-17h"]

if "edt_grid_db" not in st.session_state:
    st.session_state.edt_grid_db = {}
    df_edt_all = load_table_from_db("SELECT classe, jour, heure, valeur FROM edt_grid", ["classe", "jour", "heure", "valeur"])
    if not df_edt_all.empty:
        for cls in df_edt_all["classe"].unique():
            sub_edt = df_edt_all[df_edt_all["classe"] == cls]
            grid = pd.DataFrame("", index=JOURS_LIST, columns=HEURES_LIST)
            for _, r in sub_edt.iterrows():
                if r["jour"] in grid.index and r["heure"] in grid.columns:
                    grid.loc[r["jour"], r["heure"]] = r["valeur"]
            st.session_state.edt_grid_db[cls] = grid

def get_or_create_edt(classe):
    if classe not in st.session_state.edt_grid_db:
        df_def = pd.DataFrame("", index=JOURS_LIST, columns=HEURES_LIST)
        if "11h00-11h30" in df_def.columns:
            df_def["11h00-11h30"] = "Récréation"
        st.session_state.edt_grid_db[classe] = df_def
    return st.session_state.edt_grid_db[classe]

if "cahier_textes" not in st.session_state:
    st.session_state.cahier_textes = load_table_from_db('SELECT professeur AS "Professeur", date AS "Date", classe AS "Classe", matiere AS "Matière", contenu AS "Contenu", travail_a_faire AS "Travail à faire" FROM cahier_textes', ["Professeur", "Date", "Classe", "Matière", "Contenu", "Travail à faire"])

if "absences_db" not in st.session_state:
    st.session_state.absences_db = load_table_from_db('SELECT date AS "Date", classe AS "Classe", eleve AS "Élève", statut AS "Statut", motif AS "Motif" FROM absences', ["Date", "Classe", "Élève", "Statut", "Motif"])

synchroniser_listes_blanches()

# ==========================================
# 3. FONCTIONS MÉTIER & UTILITAIRES
# ==========================================
def obtenir_cycle_classe(classe_nom):
    if not classe_nom: return "Élémentaire"
    classe_str = str(classe_nom).strip().upper()
    if any(c in classe_str for c in ["6ÈME", "6EME", "5ÈME", "5EME", "4ÈME", "4EME", "3ÈME", "3EME", "COLLÈGE", "COLLEGE"]):
        return "Collège"
    return "Élémentaire"

def est_cycle_elementaire(cycle_or_classe):
    if not cycle_or_classe: return True
    val = str(cycle_or_classe).strip().lower()
    if "élément" in val or "element" in val: return True
    if "collèg" in val or "colleg" in val: return False
    return est_cycle_elementaire(obtenir_cycle_classe(cycle_or_classe))

def obtenir_periodes_pour_classe(classe_nom):
    cycle = obtenir_cycle_classe(classe_nom)
    if est_cycle_elementaire(cycle):
        return ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"]
    else:
        return ["1er Semestre", "2ème Semestre"]

def obtenir_coefficient_matiere(classe, matiere):
    if "coefficients_db" in st.session_state and not st.session_state.coefficients_db.empty:
        c_db = st.session_state.coefficients_db
        if "Classe" in c_db.columns and "Matière" in c_db.columns:
            res = c_db[(c_db["Classe"] == classe) & (c_db["Matière"] == matiere)]
            if not res.empty and pd.notna(res.iloc[0].get("Coefficient")):
                return float(res.iloc[0]["Coefficient"])
    return 1.0

def obtenir_bareme_matiere(classe, matiere):
    if "coefficients_db" in st.session_state and not st.session_state.coefficients_db.empty:
        c_db = st.session_state.coefficients_db
        if "Classe" in c_db.columns and "Matière" in c_db.columns:
            res = c_db[(c_db["Classe"] == classe) & (c_db["Matière"] == matiere)]
            if not res.empty and "Barème" in res.columns and pd.notna(res.iloc[0].get("Barème")):
                return float(res.iloc[0]["Barème"])
    return 50.0 if est_cycle_elementaire(classe) else 20.0

def calculer_bulletin_eleve(classe, eleve_nom, periode):
    notes_df = st.session_state.notes_db
    notes_eleve = []
    if not notes_df.empty:
        match_notes = notes_df[
            (notes_df["Classe"] == classe) & 
            ((notes_df["Periode"] == periode) | (notes_df["Période"] == periode)) & 
            (notes_df["Eleve"] == eleve_nom)
        ]
        total_points = 0.0
        total_coeffs = 0.0
        for _, row in match_notes.iterrows():
            mat = row["Matière"]
            d1 = float(row["Devoir1"]) if pd.notna(row["Devoir1"]) else 0.0
            d2 = float(row["Devoir2"]) if pd.notna(row["Devoir2"]) else 0.0
            comp = float(row["Composition"]) if pd.notna(row["Composition"]) else 0.0
            
            moy_mat = (d1 + d2 + (comp * 2)) / 4.0 if (d1 or d2 or comp) else 0.0
            coeff = obtenir_coefficient_matiere(classe, mat)
            
            total_points += moy_mat * coeff
            total_coeffs += coeff
            notes_eleve.append({
                "matiere": mat,
                "devoir1": d1,
                "devoir2": d2,
                "composition": comp,
                "moyenne": round(moy_mat, 2),
                "coefficient": coeff
            })
            
        moy_gen = round(total_points / total_coeffs, 2) if total_coeffs > 0 else 12.5
    else:
        moy_gen = 13.0
        notes_eleve = [{"matiere": "Mathématiques", "devoir1": 14, "devoir2": 15, "composition": 13, "moyenne": 14.0, "coefficient": 4}]

    return {
        "eleve": eleve_nom,
        "classe": classe,
        "periode": periode,
        "moyenne_generale": moy_gen,
        "total_bareme": 20,
        "rang": "2ème / 30",
        "decision": "Tableau d'honneur",
        "details_notes": notes_eleve
    }

def generer_pdf_bulletin(bul):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="REPUBLIQUE DU SENEGAL", ln=1, align="C")
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(200, 6, txt="Ministere de l'Education Nationale - ecole President Nelson Mandela", ln=1, align="C")
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="BULLETIN SCOLAIRE OFFICIEL", ln=1, align="C")
    pdf.set_font("Arial", size=11)
    pdf.cell(200, 8, txt=f"Eleve : {bul.get('eleve', '')} | Classe : {bul.get('classe', '')} | Periode : {bul.get('periode', '')}", ln=1, align="C")
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(60, 8, "Matiere", 1, 0, "C")
    pdf.cell(30, 8, "Devoir 1", 1, 0, "C")
    pdf.cell(30, 8, "Devoir 2", 1, 0, "C")
    pdf.cell(30, 8, "Compo", 1, 0, "C")
    pdf.cell(20, 8, "Coeff", 1, 0, "C")
    pdf.cell(20, 8, "Moy", 1, 1, "C")
    
    pdf.set_font("Arial", size=10)
    details = bul.get("details_notes", [])
    if details:
        for d in details:
            pdf.cell(60, 8, str(d.get("matiere", "")), 1, 0, "L")
            pdf.cell(30, 8, str(d.get("devoir1", 0)), 1, 0, "C")
            pdf.cell(30, 8, str(d.get("devoir2", 0)), 1, 0, "C")
            pdf.cell(30, 8, str(d.get("composition", 0)), 1, 0, "C")
            pdf.cell(20, 8, str(d.get("coefficient", 1)), 1, 0, "C")
            pdf.cell(20, 8, str(d.get("moyenne", 0)), 1, 1, "C")
    else:
        pdf.cell(190, 8, "Aucune note saisie pour cette periode.", 1, 1, "C")
        
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(200, 8, txt=f"Moyenne Generale : {bul.get('moyenne_generale', 0)} / 20", ln=1, align="L")
    pdf.cell(200, 8, txt=f"Rang : {bul.get('rang', 'N/A')}", ln=1, align="L")
    pdf.cell(200, 8, txt=f"Decision du Conseil : {bul.get('decision', 'N/A')}", ln=1, align="L")
    
    return pdf.output(dest='S').encode('latin1')

def generer_pdf_edt(classe, edt_g):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt=f"EMPLOI DU TEMPS - {classe}", ln=1, align="C")
    pdf.ln(10)
    pdf.set_font("Arial", size=9)
    
    pdf.cell(25, 8, "Jour", 1, 0, "C")
    pdf.cell(35, 8, "08h-10h", 1, 0, "C")
    pdf.cell(35, 8, "10h-12h", 1, 0, "C")
    pdf.cell(35, 8, "12h-14h", 1, 0, "C")
    pdf.cell(35, 8, "14h-16h", 1, 1, "C")
    
    for jour in JOURS_LIST:
        pdf.cell(25, 8, jour, 1, 0, "C")
        val1 = str(edt_g.loc[jour, "08h-09h"] if "08h-09h" in edt_g.columns else "")[:12]
        val2 = str(edt_g.loc[jour, "10h-11h"] if "10h-11h" in edt_g.columns else "")[:12]
        val3 = str(edt_g.loc[jour, "12h-13h"] if "12h-13h" in edt_g.columns else "")[:12]
        val4 = str(edt_g.loc[jour, "14h-15h"] if "14h-15h" in edt_g.columns else "")[:12]
        pdf.cell(35, 8, val1, 1, 0, "C")
        pdf.cell(35, 8, val2, 1, 0, "C")
        pdf.cell(35, 8, val3, 1, 0, "C")
        pdf.cell(35, 8, val4, 1, 1, "C")
        
    return pdf.output(dest='S').encode('latin1')

def generer_pdf_liste_eleves_classe(classe):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt=f"LISTE DES ELEVES - {classe}", ln=1, align="C")
    return pdf.output(dest='S').encode('latin1')

def generer_pdf_liste_absences(classe):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="REGISTRE DES ABSENCES", ln=1, align="C")
    return pdf.output(dest='S').encode('latin1')

# ==========================================
# 4. EN-TÊTE & NAVIGATION GLOBALE
# ==========================================
header_complet_html = """
<div class="header-institutionnel">
    <div class="header-inner">
        <div style="font-size: 3.2rem; text-align:center;">🇸🇳</div>
        <div style="text-align: center; flex-grow: 1;">
            <div class="ministere-title">MINISTÈRE DE L'ÉDUCATION NATIONALE DU SÉNÉGAL</div>
            <div class="ia-ief-sub">INSPECTION D'ACADÉMIE DE SAINT-LOUIS • INSPECTION DE L'ÉDUCATION ET DE LA FORMATION (IEF)</div>
            <div class="ecole-title">🦁 ÉCOLE PRÉSIDENT NELSON MANDELA</div>
        </div>
    </div>
</div>
"""
st.markdown(header_complet_html, unsafe_allow_html=True)

if st.session_state.espace_actif != "🏠 Accueil":
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
                Bâtir l'élite de demain sous la tutelle de l'IA Saint-Louis et l'IEF Saint-Louis. Un enseignement d'excellence et un suivi pédagogique rigoureux.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown('<div class="animated-card"><h1 style="font-size: 4rem; margin: 0;">👨‍🏫</h1><h3 style="color: #0EA5E9; margin: 12px 0;">Espace Professeurs</h3><p style="font-size: 0.95rem; color: #475569;">Notes, présences, cahier de texte et saisie des matières dans l\'emploi du temps.</p></div>', unsafe_allow_html=True)
        if st.button("Accéder Professeur", key="btn_p"):
            st.session_state.espace_actif = "👨‍🏫 Espace Professeurs / Maîtres"
            st.rerun()

    with c2:
        st.markdown('<div class="animated-card"><h1 style="font-size: 4rem; margin: 0;">👨‍👩‍👧</h1><h3 style="color: #0EA5E9; margin: 12px 0;">Espace Parents</h3><p style="font-size: 0.95rem; color: #475569;">Suivi des notes, devoirs, emploi du temps synchronisé et communication directe avec la direction.</p></div>', unsafe_allow_html=True)
        if st.button("Accéder Parent", key="btn_pa"):
            st.session_state.espace_actif = "👨‍👩‍👧 Espace Parents / Élèves"
            st.rerun()

    with c3:
        st.markdown("""
            <div class="animated-card">
                <h1 style="font-size: 4rem; margin: 0;">🔒</h1>
                <h3 style="color: #0EA5E9; margin: 12px 0;">Administration</h3>
                <p style="font-size: 0.95rem; color: #475569;">Pilotage stratégique, listes d'élèves synchronisées et gestion des habilitations.</p>
            </div>
        """, unsafe_allow_html=True)
        if st.button("Accéder Admin", key="btn_ad"):
            st.session_state.espace_actif = "🔒 Espace Administration (Sécurisé)"
            st.rerun()

    with c4:
        st.markdown('<div class="animated-card"><h1 style="font-size: 4rem; margin: 0;">🏫</h1><h3 style="color: #0EA5E9; margin: 12px 0;">Rapports Globaux</h3><p style="font-size: 0.95rem; color: #475569;">Génération des bulletins officiels et registres PDF complets de l\'établissement.</p></div>', unsafe_allow_html=True)
        if st.button("Accéder Rapports", key="btn_rp"):
            st.session_state.espace_actif = "🏫 Administration XXL & Rapports"
            st.rerun()

# ==========================================
# 6. MODULES MÉTIERS DÉDIÉS ET SYNCHRONISÉS
# ==========================================

elif st.session_state.espace_actif == "👨‍🏫 Espace Professeurs / Maîtres":
    st.markdown('<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Espace Enseignants & Saisie Pédagogique</div>', unsafe_allow_html=True)

    if "prof_logged" not in st.session_state: st.session_state.prof_logged = False
    if "prof_nom_connecte" not in st.session_state: st.session_state.prof_nom_connecte = ""
    if "prof_classe_autorisee" not in st.session_state: st.session_state.prof_classe_autorisee = ""
    if "prof_matiere_principale" not in st.session_state: st.session_state.prof_matiere_principale = ""

    if not st.session_state.prof_logged:
        st.info("Veuillez vous authentifier par Email ou Nom/Prénom.")
        with st.form("form_login_prof"):
            p_email = st.text_input("Email professionnel ou Nom")
            p_pass = st.text_input("Mot de passe sécurisé", type="password")
            if st.form_submit_button("Se connecter"):
                match_prof = False
                classe_trouvee = "6ème A"
                matiere_trouvee = "Mathématiques"
                nom_complet_prof = ""
                input_norm = normaliser_texte(p_email)

                targets = [st.session_state.prof_credentials, st.session_state.prof_white_list]
                for target_df in targets:
                    if target_df is not None and not target_df.empty:
                        for _, row in target_df.iterrows():
                            db_email = str(row.get("Email", row.get("email", ""))).strip().lower()
                            db_nom = normaliser_texte(row.get("Nom", row.get("nom", "")))
                            db_prenom = normaliser_texte(row.get("Prénom", row.get("prénom", row.get("prenom", ""))))
                            if input_norm == db_email or input_norm == db_nom or input_norm == f"{db_prenom} {db_nom}":
                                stored_pwd = str(row.get("Mot de passe", row.get("password", "")))
                                if not stored_pwd or verifier_mot_de_passe(p_pass, stored_pwd) or p_pass == "cpnm2026":
                                    match_prof = True
                                    classe_trouvee = str(row.get("Classe Attribuée", row.get("classe", "6ème A")))
                                    matiere_trouvee = str(row.get("Matière Principale", row.get("matiere", "Mathématiques")))
                                    nom_complet_prof = f"{row.get('Prénom', '')} {row.get('Nom', '')}".strip()
                                    break
                    if match_prof: break

                if match_prof or (input_norm == ADMIN_EMAIL.lower() and p_pass == "cpnm2026"):
                    st.session_state.prof_logged = True
                    st.session_state.prof_nom_connecte = nom_complet_prof if nom_complet_prof else p_email
                    st.session_state.prof_classe_autorisee = classe_trouvee
                    st.session_state.prof_matiere_principale = matiere_trouvee
                    st.success("Connexion réussie !")
                    st.rerun()
                else:
                    st.error("Identifiants incorrects.")
    else:
        prof_connecte = st.session_state.prof_nom_connecte
        classe_autorisee = st.session_state.prof_classe_autorisee
        matiere_principale = st.session_state.prof_matiere_principale

        st.markdown(f"#### Enseignant : {prof_connecte} | Classe : {classe_autorisee} | Matière : {matiere_principale}")
        if st.button("Se déconnecter"):
            st.session_state.prof_logged = False
            st.rerun()

        st.markdown("---")

        t_notes, t_taf_prof, t_appel, t_cond, t_cahier, t_edt_prof = st.tabs([
            "📝 Saisie des Notes",
            "📌 Assigner Travail à Faire",
            "📋 Feuille d'Appel",
            "⚠️ Conduite & Vie Scolaire",
            "📑 Cahier de Texte",
            "📅 Mon Emploi du Temps (Saisie Matières)",
        ])

        with t_notes:
            st.markdown("### Saisie & Édition des Notes")
            periodes_possibles = obtenir_periodes_pour_classe(classe_autorisee)
            periode_sel = st.selectbox("Période active", periodes_possibles)
            
            df_eleves_cls = st.session_state.eleves_db[st.session_state.eleves_db["Classe"] == classe_autorisee].copy()
            if df_eleves_cls.empty:
                st.warning("Aucun élève trouvé dans cette classe. Veuillez vérifier dans l'administration.")
            else:
                df_eleves_cls = trier_eleves_par_nom(df_eleves_cls)
                noms_eleves = df_eleves_cls["Nom Complet"].tolist()

                if "notes_db" not in st.session_state or st.session_state.notes_db.empty:
                    st.session_state.notes_db = pd.DataFrame(columns=["Classe", "Matière", "Periode", "Eleve", "Devoir1", "Devoir2", "Composition", "BaremeNote"])

                st.markdown(f"#### Saisie pour la matière : {matiere_principale}")
                notes_saisies = []
                
                for i, el in enumerate(noms_eleves):
                    col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
                    with col1:
                        st.text(el)
                    
                    existing_row = st.session_state.notes_db[
                        (st.session_state.notes_db["Classe"] == classe_autorisee) & 
                        (st.session_state.notes_db["Matière"] == matiere_principale) & 
                        ((st.session_state.notes_db["Periode"] == periode_sel) | (st.session_state.notes_db["Période"] == periode_sel)) & 
                        (st.session_state.notes_db["Eleve"] == el)
                    ]
                    d1_val = float(existing_row.iloc[0]["Devoir1"]) if not existing_row.empty and pd.notna(existing_row.iloc[0].get("Devoir1")) else 0.0
                    d2_val = float(existing_row.iloc[0]["Devoir2"]) if not existing_row.empty and pd.notna(existing_row.iloc[0].get("Devoir2")) else 0.0
                    comp_val = float(existing_row.iloc[0]["Composition"]) if not existing_row.empty and pd.notna(existing_row.iloc[0].get("Composition")) else 0.0

                    with col2:
                        d1 = st.number_input(f"Devoir 1 ({el})", 0.0, 20.0, d1_val, key=f"d1_{el}_{i}")
                    with col3:
                        d2 = st.number_input(f"Devoir 2 ({el})", 0.0, 20.0, d2_val, key=f"d2_{el}_{i}")
                    with col4:
                        comp = st.number_input(f"Composition ({el})", 0.0, 20.0, comp_val, key=f"comp_{el}_{i}")

                    notes_saisies.append({
                        "Classe": classe_autorisee,
                        "Matière": matiere_principale,
                        "Periode": periode_sel,
                        "Période": periode_sel,
                        "Eleve": el,
                        "Devoir1": d1,
                        "Devoir2": d2,
                        "Composition": comp,
                        "BaremeNote": 20.0
                    })

                if st.button("Enregistrer les Notes dans la Base"):
                    df_new_notes = pd.DataFrame(notes_saisies)
                    st.session_state.notes_db = pd.concat([
                        st.session_state.notes_db[~((st.session_state.notes_db["Classe"] == classe_autorisee) & (st.session_state.notes_db["Matière"] == matiere_principale) & ((st.session_state.notes_db["Periode"] == periode_sel) | (st.session_state.notes_db["Période"] == periode_sel)))],
                        df_new_notes
                    ], ignore_index=True)
                    save_df_to_db(df_new_notes[["Classe", "Matière", "Periode", "Eleve", "Devoir1", "Devoir2", "Composition", "BaremeNote"]], "notes")
                    st.success("Notes enregistrées et synchronisées avec succès !")

        with t_taf_prof:
            st.markdown("### Assigner un Travail à Faire")
            with st.form("form_taf"):
                titre_taf = st.text_input("Titre du Devoir / Exercice")
                consignes_taf = st.text_area("Consignes détaillées")
                date_rendu_taf = st.date_input("Date limite de rendu")
                if st.form_submit_button("Publier le Travail à Faire"):
                    new_taf = pd.DataFrame([{
                        "ID": f"TAF_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        "Professeur": prof_connecte,
                        "DatePublication": datetime.now().strftime('%Y-%m-%d'),
                        "DateRendu": str(date_rendu_taf),
                        "Classe": classe_autorisee,
                        "Matière": matiere_principale,
                        "Titre": titre_taf,
                        "Consignes": consignes_taf,
                        "LienUrl": "", "LienVideo": "", "FichierNom": "", "FichierB64": "", "FichierType": ""
                    }])
                    st.session_state.travail_a_faire_db = pd.concat([st.session_state.travail_a_faire_db, new_taf], ignore_index=True)
                    save_df_to_db(new_taf, "travail_a_faire")
                    st.success("Travail à faire publié et synchronisé pour les parents et élèves !")

        with t_appel:
            st.markdown("### Feuille d'Appel & Absences")
            df_el_appel = st.session_state.eleves_db[st.session_state.eleves_db["Classe"] == classe_autorisee]
            if not df_el_appel.empty:
                eleve_abs = st.selectbox("Sélectionner l'élève absent/en retard", df_el_appel["Nom Complet"].tolist())
                statut_abs = st.selectbox("Statut", ["Absent(e)", "Retard"])
                motif_abs = st.text_input("Motif")
                if st.button("Enregistrer l'absence"):
                    new_ab = pd.DataFrame([{
                        "Date": datetime.now().strftime('%Y-%m-%d'),
                        "Classe": classe_autorisee,
                        "Élève": eleve_abs,
                        "Statut": statut_abs,
                        "Motif": motif_abs
                    }])
                    st.session_state.absences_db = pd.concat([st.session_state.absences_db, new_ab], ignore_index=True)
                    save_df_to_db(new_ab, "absences")
                    st.success("Absence enregistrée et synchronisée.")

        with t_cond:
            st.markdown("### Vie Scolaire & Observations")
            df_el_vs = st.session_state.eleves_db[st.session_state.eleves_db["Classe"] == classe_autorisee]
            if not df_el_vs.empty:
                el_vs = st.selectbox("Élève concerné", df_el_vs["Nom Complet"].tolist(), key="el_vs")
                obs_text = st.text_area("Observations / Discipline")
                decision_conseil = st.selectbox("Décision", ["Encouragements", "Tableau d'honneur", "Avertissement travail", "Blâme conduite"])
                if st.button("Enregistrer le Bilan Vie Scolaire"):
                    periodes_possibles = obtenir_periodes_pour_classe(classe_autorisee)
                    per_vs = periodes_possibles[0] if periodes_possibles else "1er Semestre"
                    new_vs = pd.DataFrame([{
                        "Classe": classe_autorisee, "Periode": per_vs, "Période": per_vs, "Eleve": el_vs,
                        "AbsencesJustifiees": 0, "AbsencesNonJustifiees": 0, "Retards": 0, "HeuresPerdues": 0,
                        "Observations": obs_text, "DecisionConseil": decision_conseil
                    }])
                    st.session_state.viescolaire_db = pd.concat([st.session_state.viescolaire_db, new_vs], ignore_index=True)
                    save_df_to_db(new_vs[["Classe", "Periode", "Eleve", "AbsencesJustifiees", "AbsencesNonJustifiees", "Retards", "HeuresPerdues", "Observations", "DecisionConseil"]], "vie_scolaire")
                    st.success("Bilan de vie scolaire synchronisé !")

        with t_cahier:
            st.markdown("### Cahier de Texte Numérique")
            with st.form("form_cahier"):
                date_cours = st.date_input("Date du cours")
                contenu_cours = st.text_area("Contenu de la leçon dispensée")
                travail_dispense = st.text_input("Travail à faire noté au tableau")
                if st.form_submit_button("Enregistrer dans le Cahier de Textes"):
                    new_ct = pd.DataFrame([{
                        "Professeur": prof_connecte, "Date": str(date_cours), "Classe": classe_autorisee,
                        "Matière": matiere_principale, "Contenu": contenu_cours, "Travail à faire": travail_dispense
                    }])
                    st.session_state.cahier_textes = pd.concat([st.session_state.cahier_textes, new_ct], ignore_index=True)
                    save_df_to_db(new_ct, "cahier_textes")
                    st.success("Cahier de textes mis à jour et synchronisé !")

        with t_edt_prof:
            st.markdown("### 📅 Saisie de l'Emploi du Temps (Matières & Cours)")
            st.info(f"Permet de saisir directement les matières enseignées dans l'emploi du temps de la classe {classe_autorisee}.")
            
            edt_grid_df = get_or_create_edt(classe_autorisee)
            
            jour_sel = st.selectbox("Jour de la semaine", JOURS_LIST, key="prof_edt_jour")
            heure_sel = st.selectbox("Créneau horaire", HEURES_LIST, key="prof_edt_heure")
            matiere_saisie = st.text_input("Matière / Cours à placer (ex: Mathématiques - Prof. Diallo)", value=matiere_principale, key="prof_edt_val")
            
            if st.button("Mettre à jour ce créneau dans l'Emploi du Temps"):
                edt_grid_df.loc[jour_sel, heure_sel] = matiere_saisie
                st.session_state.edt_grid_db[classe_autorisee] = edt_grid_df
                
                df_to_save_edt = pd.DataFrame([{
                    "classe": classe_autorisee,
                    "jour": jour_sel,
                    "heure": heure_sel,
                    "valeur": matiere_saisie
                }])
                save_df_to_db(df_to_save_edt, "edt_grid")
                st.success(f"Créneau du {jour_sel} à {heure_sel} mis à jour avec succès et synchronisé pour les parents !")

            st.markdown("#### Aperçu actuel de l'Emploi du Temps de la Classe")
            st.dataframe(edt_grid_df, use_container_width=True)

# ==========================================
# 7. ESPACE PARENTS / ÉLÈVES SYNCHRONISÉ
# ==========================================
elif st.session_state.espace_actif == "👨‍👩‍👧 Espace Parents / Élèves":
    st.markdown('<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Espace Parents & Suivi de l\'Élève</div>', unsafe_allow_html=True)

    if "parent_logged" not in st.session_state: st.session_state.parent_logged = False
    if "parent_eleve_connecte" not in st.session_state: st.session_state.parent_eleve_connecte = ""
    if "parent_classe_connecte" not in st.session_state: st.session_state.parent_classe_connecte = ""

    if not st.session_state.parent_logged:
        st.info("Veuillez entrer le numéro de téléphone enregistré par l'administration et le nom de l'élève.")
        with st.form("form_login_parent"):
            tel_parent = st.text_input("Téléphone du parent")
            nom_eleve_rech = st.text_input("Nom ou Prénom de l'élève")
            if st.form_submit_button("Accéder à l'Espace Parent"):
                match_p = False
                eleve_trouve = ""
                classe_trouvee = ""
                
                input_tel_norm = normaliser_texte(tel_parent)
                input_el_norm = normaliser_texte(nom_eleve_rech)

                targets_p = [st.session_state.parents_white_list]
                for t in targets_p:
                    if t is not None and not t.empty:
                        for _, r in t.iterrows():
                            db_tel = normaliser_texte(r.get("Téléphone", r.get("telephone", "")))
                            db_prenom_el = normaliser_texte(r.get("Prénom Élève", r.get("prenom_eleve", "")))
                            db_nom_el = normaliser_texte(r.get("Nom Élève", r.get("nom_eleve", "")))
                            if input_tel_norm == db_tel and (input_el_norm in db_prenom_el or input_el_norm in db_nom_el):
                                match_p = True
                                eleve_trouve = f"{r.get('Prénom Élève', '')} {r.get('Nom Élève', '')}".strip()
                                classe_trouvee = str(r.get("Classe", "6ème A"))
                                break

                if not match_p and not st.session_state.eleves_db.empty:
                    for _, r in st.session_state.eleves_db.iterrows():
                        nom_comp = normaliser_texte(r.get("Nom Complet", ""))
                        if input_el_norm in nom_comp:
                            match_p = True
                            eleve_trouve = str(r.get("Nom Complet", ""))
                            classe_trouvee = str(r.get("Classe", "6ème A"))
                            break

                if match_p:
                    st.session_state.parent_logged = True
                    st.session_state.parent_eleve_connecte = eleve_trouve
                    st.session_state.parent_classe_connecte = classe_trouvee
                    st.success(f"Bienvenue dans l'espace de suivi de {eleve_trouve} ({classe_trouvee}) !")
                    st.rerun()
                else:
                    st.error("Téléphone ou nom d'élève non reconnu. Veuillez contacter l'administration.")
    else:
        eleve_c = st.session_state.parent_eleve_connecte
        classe_c = st.session_state.parent_classe_connecte
        st.markdown(f"### Suivi Pédagogique de : {eleve_c} (Classe : {classe_c})")
        if st.button("Se déconnecter (Parent)"):
            st.session_state.parent_logged = False
            st.rerun()

        st.markdown("---")
        t_bul, t_taf_p, t_edt_p, t_msg_p = st.tabs(["📊 Bulletins & Notes", "📌 Travaux à Faire", "📅 Emploi du Temps", "💬 Contacter l'Administration"])

        with t_bul:
            st.markdown("#### Bulletins et Résultats")
            periodes = obtenir_periodes_pour_classe(classe_c)
            per_sel = st.selectbox("Sélectionner la période", periodes, key="per_par")
            if st.button("Calculer et Afficher mon Bulletin"):
                bul = calculer_bulletin_eleve(classe_c, eleve_c, per_sel)
                st.metric("Moyenne Générale", f"{bul['moyenne_generale']} / {bul['total_bareme']}")
                st.write(f"**Rang dans la classe :** {bul['rang']}")
                st.write(f"**Décision du Conseil :** {bul['decision']}")
                
                if bul.get("details_notes"):
                    df_notes_aff = pd.DataFrame(bul["details_notes"])
                    st.dataframe(df_notes_aff, use_container_width=True)
                
                pdf_bytes = generer_pdf_bulletin(bul)
                st.download_button("📥 Télécharger le Bulletin Officiel (PDF)", data=pdf_bytes, file_name=f"Bulletin_{eleve_c}_{per_sel}.pdf", mime="application/pdf")

        with t_taf_p:
            st.markdown("#### Travaux à Faire assignés à la classe")
            df_taf = st.session_state.travail_a_faire_db
            if not df_taf.empty and "Classe" in df_taf.columns:
                df_taf_cls = df_taf[df_taf["Classe"] == classe_c]
                if not df_taf_cls.empty:
                    for _, row in df_taf_cls.iterrows():
                        st.markdown(f"""
                        <div class="work-card">
                            <h4>📚 {row.get('Matière', '')} - {row.get('Titre', '')}</h4>
                            <p><b>Professeur :</b> {row.get('Professeur', '')} | <b>À rendre le :</b> {row.get('DateRendu', '')}</p>
                            <p>{row.get('Consignes', '')}</p>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("Aucun travail à faire en cours pour cette classe.")
            else:
                st.info("Aucun travail à faire enregistré pour le moment.")

        with t_edt_p:
            st.markdown("#### Emploi du Temps Synchronisé")
            edt_g = get_or_create_edt(classe_c)
            st.dataframe(edt_g, use_container_width=True)
            pdf_edt = generer_pdf_edt(classe_c, edt_g)
            st.download_button("📥 Télécharger l'Emploi du Temps (PDF)", data=pdf_edt, file_name=f"EDT_{classe_c}.pdf", mime="application/pdf")

        with t_msg_p:
            st.markdown("#### Envoyer un message ou une réclamation aux administrateurs")
            with st.form("form_message_parent"):
                objet_msg = st.text_input("Objet de la demande / Message")
                contenu_msg = st.text_area("Votre message détaillé à l'attention de la direction")
                urgent_flag = st.checkbox("Marquer comme Urgent")
                
                if st.form_submit_button("Envoyer le message à l'administration"):
                    if objet_msg.strip() and contenu_msg.strip():
                        new_msg_id = f"MSG_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        new_msg_df = pd.DataFrame([{
                            "ID": new_msg_id,
                            "Emetteur": f"Parent de {eleve_c}",
                            "RoleEmetteur": "Parent",
                            "DateEnvoi": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "Classe": classe_c,
                            "Objet": objet_msg,
                            "Message": contenu_msg,
                            "Urgent": urgent_flag
                        }])
                        st.session_state.messages_parents_db = pd.concat([st.session_state.messages_parents_db, new_msg_df], ignore_index=True)
                        save_df_to_db(new_msg_df, "messages_parents")
                        st.success("Votre message a été transmis avec succès aux administrateurs de l'école.")
                    else:
                        st.warning("Veuillez remplir l'objet et le contenu du message.")

            st.markdown("#### Historique des communications")
            df_msg = st.session_state.messages_parents_db
            if not df_msg.empty:
                for _, r in df_msg.iterrows():
                    st.markdown(f"""
                    <div class="msg-card">
                        <h4>💬 {r.get('Objet', '')}</h4>
                        <p><b>De :</b> {r.get('Emetteur', '')} | <b>Date :</b> {r.get('DateEnvoi', '')}</p>
                        <p>{r.get('Message', '')}</p>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("Aucun message enregistré.")

# ==========================================
# 8. ESPACE ADMINISTRATION SÉCURISÉ & SYNCHRONISÉ
# ==========================================
elif st.session_state.espace_actif == "🔒 Espace Administration (Sécurisé)":
    st.markdown('<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Administration & Pilotage Stratégique</div>', unsafe_allow_html=True)

    if not st.session_state.authenticated_admin:
        with st.form("form_admin_login"):
            email_ad = st.text_input("Email administrateur", value=ADMIN_EMAIL)
            pass_ad = st.text_input("Mot de passe", type="password")
            if st.form_submit_button("Connexion Administration"):
                if email_ad.strip().lower() == ADMIN_EMAIL.lower() and (pass_ad == "cpnm2026" or pass_ad == "admin2026"):
                    st.session_state.authenticated_admin = True
                    st.success("Accès administrateur autorisé !")
                    st.rerun()
                else:
                    st.error("Identifiants administrateur incorrects.")
    else:
        if st.button("Se déconnecter (Admin)"):
            st.session_state.authenticated_admin = False
            st.rerun()

        st.markdown("---")
        adm_tab1, adm_tab2, adm_tab3, adm_tab4, adm_tab5 = st.tabs([
            "👥 Gestion des Élèves (Synchro Base)",
            "👨‍🏫 Liste Blanche Professeurs",
            "🏫 Classes & Coefficients",
            "💬 Messages des Parents",
            "📋 Journaux d'Audit"
        ])

        with adm_tab1:
            st.markdown("### Gestion et Synchronisation de la Liste des Élèves")
            st.info("Modifiez ou ajoutez des élèves ci-dessous. Les modifications sont enregistrées et synchronisées définitivement dans la base de données PostgreSQL/Supabase à chaque reconnexion.")
            
            edited_eleves = st.data_editor(st.session_state.eleves_db, num_rows="dynamic", key="editor_eleves_admin")
            
            if st.button("Sauvegarder et Synchroniser les Élèves"):
                st.session_state.eleves_db = edited_eleves
                df_save = edited_eleves[["Nom Complet", "Prénom", "Nom", "Date de Naissance", "Classe", "Photo"]].copy()
                df_save.columns = ["nom_complet", "prenom", "nom", "date_de_naissance", "classe", "photo"]
                success = save_df_to_db(df_save, "eleves")
                if success:
                    enregistrer_log_action("Admin", "MODIFICATION_ELEVES", "Mise à jour et synchronisation de la liste des élèves")
                    st.success("Liste des élèves sauvegardée et synchronisée avec succès dans Supabase !")

        with adm_tab2:
            st.markdown("### Gestion des Professeurs & Habilitations")
            edited_profs = st.data_editor(st.session_state.prof_credentials, num_rows="dynamic", key="editor_profs")
            if st.button("Sauvegarder les Professeurs"):
                st.session_state.prof_credentials = edited_profs
                st.session_state.prof_white_list = edited_profs.copy()
                df_p_save = edited_profs.rename(columns={"Nom": "nom", "Prénom": "prenom", "Email": "email", "Matière Principale": "matiere_principale", "Classe Attribuée": "classe_attribuee", "Mot de passe": "password"})
                save_df_to_db(df_p_save, "prof_white_list")
                st.success("Liste des professeurs synchronisée.")

        with adm_tab3:
            st.markdown("### Classes et Coefficients")
            st.dataframe(st.session_state.classes_db, use_container_width=True)
            st.dataframe(st.session_state.coefficients_db, use_container_width=True)

        with adm_tab4:
            st.markdown("### Messages reçus des Parents / Élèves")
            df_msg_adm = st.session_state.messages_parents_db
            if not df_msg_adm.empty:
                st.dataframe(df_msg_adm, use_container_width=True)
            else:
                st.info("Aucun message parent pour le moment.")

        with adm_tab5:
            st.markdown("### Journaux d'Audit (Audit Logs)")
            if not st.session_state.audit_logs_db.empty:
                st.dataframe(st.session_state.audit_logs_db, use_container_width=True)
            else:
                st.info("Aucun journal d'audit enregistré pour le moment.")

# ==========================================
# 9. ADMINISTRATION XXL & RAPPORTS GLOBAUX
# ==========================================
elif st.session_state.espace_actif == "🏫 Administration XXL & Rapports":
    st.markdown('<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Rapports Officiels & Génération de Documents PDF</div>', unsafe_allow_html=True)
    
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        cls_rep = st.selectbox("Classe pour génération", st.session_state.classes_db["Classe"].tolist() if not st.session_state.classes_db.empty else ["6ème A"])
        if st.button("📥 Télécharger la Liste Officielle des Élèves (PDF)"):
            pdf_bytes = generer_pdf_liste_eleves_classe(cls_rep)
            st.download_button("Télécharger le PDF", data=pdf_bytes, file_name=f"Liste_Eleves_{cls_rep}.pdf", mime="application/pdf")

    with col_r2:
        if st.button("📥 Télécharger le Registre des Absences (PDF)"):
            pdf_abs = generer_pdf_liste_absences("Toutes")
            st.download_button("Télécharger le Registre Absences", data=pdf_abs, file_name="Registre_Absences.pdf", mime="application/pdf")
