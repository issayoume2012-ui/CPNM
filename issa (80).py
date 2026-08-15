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
            # Table Audit Logs
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    horodatage VARCHAR(50),
                    acteur VARCHAR(255),
                    action VARCHAR(255),
                    details TEXT
                );
            """)
            # Table Admin Credentials / White List
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
            # Table Prof Credentials / White List
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
            # Table Parents White List
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
            # Table Classes
            cur.execute("""
                CREATE TABLE IF NOT EXISTS classes (
                    id SERIAL PRIMARY KEY,
                    classe VARCHAR(255) UNIQUE NOT NULL,
                    cycle VARCHAR(255),
                    professeur_responsable VARCHAR(255)
                );
            """)
            # Table Eleves
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
            # Table Matieres
            cur.execute("""
                CREATE TABLE IF NOT EXISTS matieres (
                    id SERIAL PRIMARY KEY,
                    matiere VARCHAR(255),
                    cycle VARCHAR(255),
                    coefficient FLOAT,
                    bareme FLOAT
                );
            """)
            # Table Coefficients
            cur.execute("""
                CREATE TABLE IF NOT EXISTS coefficients (
                    id SERIAL PRIMARY KEY,
                    classe VARCHAR(255),
                    matiere VARCHAR(255),
                    coefficient FLOAT,
                    bareme FLOAT
                );
            """)
            # Table Periodes
            cur.execute("""
                CREATE TABLE IF NOT EXISTS periodes (
                    id SERIAL PRIMARY KEY,
                    periode VARCHAR(255),
                    statut VARCHAR(50),
                    cycle VARCHAR(255)
                );
            """)
            # Table Notes
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
            # Table Vie Scolaire
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
            # Table Travail à faire
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
            # Table Messages Parents
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
            # Table Emploi du Temps Grid
            cur.execute("""
                CREATE TABLE IF NOT EXISTS edt_grid (
                    id SERIAL PRIMARY KEY,
                    classe VARCHAR(255),
                    jour VARCHAR(50),
                    heure VARCHAR(50),
                    valeur TEXT
                );
            """)
            # Table Cahier de Textes
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
            # Table Absences
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

# Initialiser les tables Supabase/PostgreSQL dès le lancement
init_db()

# Fonctions de chargement et de synchronisation des données Supabase/PostgreSQL
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

def save_df_to_db(df, table_name):
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {table_name};")
            if not df.empty:
                # Mappage pour convertir les noms de colonnes conviviaux du DataFrame vers les colonnes SQL exactes
                mapping_cols = {
                    "Nom": "nom",
                    "Prénom": "prenom",
                    "Email": "email",
                    "Matière Principale": "matiere_principale",
                    "Classe Attribuée": "classe_attribuee",
                    "Mot de passe": "password"
                }
                df_to_save = df.rename(columns=mapping_cols)
                cols_sql = [c for c in df_to_save.columns if c in mapping_cols.values()]
                
                if cols_sql:
                    sub_df = df_to_save[cols_sql]
                    cols_str = ",".join(cols_sql)
                    vals_str = ",".join(["%s"] * len(cols_sql))
                    query = f"INSERT INTO {table_name} ({cols_str}) VALUES ({vals_str})"
                    cur.executemany(query, sub_df.values.tolist())
            conn.commit()
    except Exception as e:
        conn.rollback()
        st.error(f"Erreur de sauvegarde dans {table_name} : {e}")
    finally:
        conn.close()

# ==========================================
# 0. BIS. GESTION DE LA SÉCURITÉ LOCALE
# ==========================================
def hacher_mot_de_passe(password: str) -> str:
    if not password: return ""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verifier_mot_de_passe(password: str, hashed: str) -> bool:
    if not password or not hashed: return False
    try:
        if not hashed.startswith("$2b$") and not hashed.startswith("$2a$"):
            return password == hashed
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return password == hashed

def normaliser_texte(texte):
    if not texte: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(texte)) if unicodedata.category(c) != 'Mn').strip().lower()

def nettoyer_texte_pdf(texte):
    if not texte: return ""
    return str(texte).encode('latin-1', 'replace').decode('latin-1')

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
    return df_copy.reset_index(drop=True)

def synchroniser_listes_blanches():
    """Maintient la cohérence absolue et bidirectionnelle des accès professeurs depuis la base."""
    df_prof_db = load_table_from_db('SELECT nom AS "Nom", prenom AS "Prénom", email AS "Email", matiere_principale AS "Matière Principale", classe_attribuee AS "Classe Attribuée", password AS "Mot de passe" FROM prof_white_list', ["Nom", "Prénom", "Email", "Matière Principale", "Classe Attribuée", "Mot de passe"])
    if not df_prof_db.empty:
        st.session_state.prof_credentials = df_prof_db
        st.session_state.prof_white_list = df_prof_db.copy()
    else:
        if "prof_credentials" in st.session_state and not st.session_state.prof_credentials.empty:
            st.session_state.prof_white_list = st.session_state.prof_credentials.copy()

def obtenir_periodes_pour_classe(classe):
    return ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"]

def calculer_bulletin_eleve(classe, eleve, periode):
    return {}

def generer_pdf_bulletin(bul_data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Bulletin Scolaire Officiel", ln=True, align="C")
    return bytes(pdf.output())

# ==========================================
# 0. TER. GESTION DU DESIGN ET DU DRAPEAU
# ==========================================
def assistant_ia_repondre(question: str) -> str:
    q = question.lower()
    if "bulletin" in q or "note" in q:
        return "Les bulletins d'excellence sont générés automatiquement au format standardisé sous l'autorité de l'IA Saint-Louis et IEF Saint-Louis, garantissant rigueur et équité pour chaque élève."
    elif "prof" in q or "enseignant" in q:
        return "Nos enseignants d'élite s'engagent au quotidien pour encadrer les notes, le cahier de texte, le travail à faire et le suivi personnalisé."
    elif "parent" in q or "élève" in q:
        return "Les parents disposent d'un suivi pédagogique transparent en temps réel (travaux à faire, devoirs, pièces jointes, emploi du temps et vie scolaire) pour accompagner la réussite de leurs enfants."
    elif "admin" in q or "administrateur" in q:
        return "L'administration pilote l'établissement avec dévouement pour maintenir les plus hauts standards de qualité académique."
    return "École Président Nelson Mandela - Excellence, Discipline et Réussite au cœur du Système Pédagogique (IA Saint-Louis / IEF Saint-Louis)."

# ==========================================
# 1. CONFIGURATION DE LA PAGE & DESIGN XXL
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
    .header-institutionnel { background: linear-gradient(135deg, #0EA5E9 0%, #2563EB 50%, #1D4ED8 100%); padding: 10px; border-radius: 32px; box-shadow: 0 25px 50px rgba(14, 165, 233, 0.3); margin-bottom: 35px; }
    .header-inner { background: rgba(255, 255, 255, 0.99); backdrop-filter: blur(20px); padding: 25px 35px; border-radius: 26px; display: flex; align-items: center; justify-content: space-between; gap: 25px; }
    .header-text { text-align: center; flex-grow: 1; }
    .ministere-title { color: #0F172A; font-size: clamp(1.2rem, 2.5vw, 1.9rem); font-weight: 900; text-transform: uppercase; letter-spacing: 1.2px; margin: 0; }
    .ia-ief-sub { color: #1E3A8A; font-size: clamp(0.9rem, 1.8vw, 1.2rem); font-weight: 700; margin: 6px 0; letter-spacing: 0.5px; }
    .ecole-title { color: #0EA5E9; font-size: clamp(1.4rem, 2.8vw, 2.3rem); font-weight: 900; margin: 8px 0 0 0; text-transform: uppercase; }
    .stButton>button { background: linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%) !important; color: #FFFFFF !important; border-radius: 18px !important; font-weight: 800 !important; border: none !important; padding: 0.9rem 1.5rem !important; width: 100% !important; min-height: 56px !important; font-size: 1.1rem !important; box-shadow: 0 10px 25px rgba(14, 165, 233, 0.35) !important; }
    .stTextInput input, .stSelectbox select, .stNumberInput input, .stTextArea textarea { background-color: #FFFFFF !important; color: #0F172A !important; border: 2px solid #7DD3FC !important; border-radius: 16px !important; font-weight: 600 !important; }
    h1, h2, h3, h4, h5, h6, label, p, span { color: #0F172A !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("<style>[data-testid=\"stToolbar\"] { display: none; } footer { visibility: hidden; }</style>", unsafe_allow_html=True)

# ==========================================
# 2. INITIALISATION DES DONNÉES
# ==========================================
if "espace_actif" not in st.session_state:
    st.session_state.espace_actif = "🏠 Accueil"

if "authenticated_admin" not in st.session_state:
    st.session_state.authenticated_admin = False

if "audit_logs_db" not in st.session_state:
    st.session_state.audit_logs_db = load_table_from_db("SELECT horodatage, acteur, action, details FROM audit_logs", ["horodatage", "acteur", "action", "details"])

if "admin_credentials" not in st.session_state:
    df_admin = load_table_from_db('SELECT nom AS "Nom", prenom AS "Prénom", email AS "Email", password AS "Mot de passe", niveau_acces AS "Niveau d\'accès" FROM admin_white_list', ["Nom", "Prénom", "Email", "Mot de passe", "Niveau d'accès"])
    if df_admin.empty:
        st.session_state.admin_credentials = pd.DataFrame([{
            "Nom": "Principal",
            "Prénom": "Admin",
            "Email": ADMIN_EMAIL,
            "Mot de passe": hacher_mot_de_passe("cpnm2026"),
            "Niveau d'accès": "Super-Admin Ayant-Droit",
        }])
    else:
        st.session_state.admin_credentials = df_admin

if "admin_white_list" not in st.session_state:
    st.session_state.admin_white_list = st.session_state.admin_credentials.copy()

if "prof_credentials" not in st.session_state:
    df_prof = load_table_from_db('SELECT nom AS "Nom", prenom AS "Prénom", email AS "Email", matiere_principale AS "Matière Principale", classe_attribuee AS "Classe Attribuée", password AS "Mot de passe" FROM prof_white_list', ["Nom", "Prénom", "Email", "Matière Principale", "Classe Attribuée", "Mot de passe"])
    st.session_state.prof_credentials = df_prof

for col in ["Nom", "Prénom", "Email", "Matière Principale", "Classe Attribuée", "Mot de passe"]:
    if col not in st.session_state.prof_credentials.columns:
        st.session_state.prof_credentials[col] = ""

if "prof_white_list" not in st.session_state:
    st.session_state.prof_white_list = st.session_state.prof_credentials.copy()

if "parents_white_list" not in st.session_state:
    st.session_state.parents_white_list = load_table_from_db('SELECT telephone AS "Téléphone", prenom_eleve AS "Prénom Élève", nom_eleve AS "Nom Élève", annee_naissance AS "Année Naissance", classe AS "Classe" FROM parents_white_list', ["Téléphone", "Prénom Élève", "Nom Élève", "Année Naissance", "Classe"])

if "classes_db" not in st.session_state:
    df_classes = load_table_from_db('SELECT classe AS "Classe", cycle AS "Cycle", professeur_responsable AS "Professeur Responsable" FROM classes', ["Classe", "Cycle", "Professeur Responsable"])
    if df_classes.empty:
        st.session_state.classes_db = pd.DataFrame(columns=["Classe", "Cycle", "Professeur Responsable"], data=[["6ème A", "Collège", "Prof. Math"], ["CP", "Élémentaire", "Prof. Élémen"]])
    else:
        st.session_state.classes_db = df_classes

if "eleves_db" not in st.session_state:
    st.session_state.eleves_db = load_table_from_db('SELECT nom_complet AS "Nom Complet", prenom AS "Prénom", nom AS "Nom", date_de_naissance AS "Date de Naissance", classe AS "Classe", photo AS "Photo" FROM eleves', ["Nom Complet", "Prénom", "Nom", "Date de Naissance", "Classe", "Photo"])

for col_req in ["Nom Complet", "Prénom", "Nom", "Date de Naissance", "Classe", "Photo"]:
    if col_req not in st.session_state.eleves_db.columns:
        st.session_state.eleves_db[col_req] = ""

if not st.session_state.eleves_db.empty:
    st.session_state.eleves_db = trier_eleves_par_nom(st.session_state.eleves_db)

if "notes_db" not in st.session_state:
    st.session_state.notes_db = load_table_from_db('SELECT classe AS "Classe", matiere AS "Matière", periode AS "Periode", periode AS "Période", eleve AS "Eleve", devoir1 AS "Devoir1", devoir2 AS "Devoir2", composition AS "Composition", baremenote AS "BaremeNote" FROM notes', ["Classe", "Matière", "Periode", "Période", "Eleve", "Devoir1", "Devoir2", "Composition", "BaremeNote"])

if isinstance(st.session_state.notes_db, pd.DataFrame):
    st.session_state.notes_db = st.session_state.notes_db.reset_index(drop=True)
    if "BaremeNote" not in st.session_state.notes_db.columns:
        st.session_state.notes_db["BaremeNote"] = 20.0

synchroniser_listes_blanches()

# ==========================================
# 3. INTERFACE PRINCIPALE & NAVIGATION
# ==========================================
st.markdown(
    """
    <div class="header-institutionnel">
        <div class="header-inner">
            <div class="header-text">
                <p class="ministere-title">République du Sénégal — Un Peuple - Un But - Une Foi</p>
                <p class="ia-ief-sub">Ministère de l'Éducation Nationale • IA Saint-Louis • IEF Saint-Louis</p>
                <h1 class="ecole-title">École Président Nelson Mandela</h1>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

menu_cols = st.columns(5)
espaces = ["🏠 Accueil", "🛡️ Espace Admin", "👨‍🏫 Espace Professeur", "👪 Espace Parents", "🤖 Assistant IA"]

for idx, esp in enumerate(espaces):
    with menu_cols[idx]:
        if st.button(esp, key=f"nav_{idx}"):
            st.session_state.espace_actif = esp
            st.rerun()

st.markdown("---")

# ==========================================
# 4. GESTION DES ESPACES
# ==========================================
if st.session_state.espace_actif == "🏠 Accueil":
    st.markdown("### Bienvenue sur le Portail National de l'École Président Nelson Mandela")
    st.markdown("Sélectionnez votre espace dans le menu supérieur pour accéder aux services administratifs, pédagogiques et au suivi personnalisé en temps réel.")

elif st.session_state.espace_actif == "🛡️ Espace Admin":
    st.markdown("## 🛡️ Espace Administration & Sécurité")
    if not st.session_state.authenticated_admin:
        email_admin = st.text_input("E-mail Administrateur", key="adm_email_input")
        pwd_admin = st.text_input("Mot de passe Administrateur", type="password", key="adm_pwd_input")
        if st.button("Se connecter à l'Administration"):
            df_adm_cred = st.session_state.admin_credentials
            match = df_adm_cred[df_adm_cred["Email"].str.strip().str.lower() == email_admin.strip().lower()]
            if not match.empty and verifier_mot_de_passe(pwd_admin, match.iloc[0]["Mot de passe"]):
                st.session_state.authenticated_admin = True
                st.success("Connexion administrateur réussie !")
                enregistrer_log_action(email_admin, "Connexion Admin", "Succès")
                st.rerun()
            else:
                st.error("Identifiants administrateur incorrects.")
    else:
        st.success("Administrateur connecté avec succès.")
        if st.button("Se déconnecter"):
            st.session_state.authenticated_admin = False
            st.rerun()
        
        tab_admin1, tab_admin2 = st.tabs(["Gestion Professeurs (Liste Blanche)", "Gestion Classes & Élèves"])
        with tab_admin1:
            st.markdown("### Enregistrer ou modifier un professeur dans la liste blanche")
            with st.form("form_ajout_prof"):
                p_nom = st.text_input("Nom du Professeur")
                p_prenom = st.text_input("Prénom du Professeur")
                p_email = st.text_input("E-mail du Professeur")
                p_mat = st.text_input("Matière Principale")
                p_cls = st.text_input("Classe Attribuée")
                p_pwd = st.text_input("Mot de passe", type="password")
                submit_prof = st.form_submit_button("Enregistrer le Professeur")
                if submit_prof:
                    if p_email and p_nom:
                        hashed_p = hacher_mot_de_passe(p_pwd if p_pwd else "prof2026")
                        new_row = pd.DataFrame([{
                            "Nom": p_nom.strip(),
                            "Prénom": p_prenom.strip(),
                            "Email": p_email.strip().lower(),
                            "Matière Principale": p_mat.strip(),
                            "Classe Attribuée": p_cls.strip(),
                            "Mot de passe": hashed_p
                        }])
                        st.session_state.prof_credentials = pd.concat([st.session_state.prof_credentials, new_row], ignore_index=True)
                        save_df_to_db(st.session_state.prof_credentials, "prof_white_list")
                        synchroniser_listes_blanches()
                        st.success(f"Professeur {p_nom} {p_prenom} ajouté avec succès dans la base et la liste blanche !")
                        enregistrer_log_action(p_email, "Ajout Professeur", f"Classe: {p_cls}, Matière: {p_mat}")
                    else:
                        st.error("Veuillez renseigner au moins l'e-mail et le nom.")
            
            st.markdown("### Professeurs actuellement répertoriés")
            synchroniser_listes_blanches()
            st.dataframe(st.session_state.prof_credentials, use_container_width=True)

        with tab_admin2:
            st.markdown("### Gestion des Classes et Élèves")
            st.dataframe(st.session_state.classes_db, use_container_width=True)

elif st.session_state.espace_actif == "👨‍🏫 Espace Professeur":
    st.markdown("## 👨‍🏫 Espace Enseignant")
    synchroniser_listes_blanches()
    st.info("Module enseignant opérationnel.")

elif st.session_state.espace_actif == "👪 Espace Parents":
    st.markdown("## 👪 Espace Parents")
    st.info("Module parents opérationnel.")

elif st.session_state.espace_actif == "🤖 Assistant IA":
    st.markdown("## 🤖 Assistant Pédagogique Intelligent")
    question_user = st.text_input("Posez votre question :")
    if st.button("Interroger l'Assistant IA"):
        if question_user:
            st.info(assistant_ia_repondre(question_user))
        else:
            st.warning("Veuillez saisir une question.")
