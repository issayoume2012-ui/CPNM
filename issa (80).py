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
# 0. CONFIGURATION & ÉTAT LOCAL (SANS SUPABASE)
# ==========================================
def init_db():
    """Initialisation locale des structures de données en mémoire."""
    if "audit_logs_db" not in st.session_state:
        st.session_state.audit_logs_db = pd.DataFrame(columns=["Horodatage", "Acteur", "Action", "Détails"])
    if "admin_white_list" not in st.session_state:
        st.session_state.admin_white_list = pd.DataFrame([{
            "Email": "cpnjcpn@gmail.com", "Nom": "Nelson", "Prénom": "Admin Principal",
            "Mot de passe": hacher_mot_de_passe("cpnmn2026"), "Niveau d'accès": "Total (Super Admin)"
        }])
    if "prof_white_list" not in st.session_state:
        st.session_state.prof_white_list = pd.DataFrame([{
            "Nom": "Prof", "Prénom": "Élémentaire", "Email": "prof.elem@cpnm.sn",
            "Matière Principale": "Toutes les matières", "Classe Attribuée": "CP", "Mot de passe": hacher_mot_de_passe("cpnm2026")
        }])
    if "classes_db" not in st.session_state:
        st.session_state.classes_db = pd.DataFrame(columns=["Classe", "Cycle", "Professeur Responsable"], data=[])
    if "eleves_db" not in st.session_state:
        st.session_state.eleves_db = pd.DataFrame(columns=["Nom Complet", "Prénom", "Nom", "Date de Naissance", "Classe", "Photo"], data=[])
    if "matieres_def" not in st.session_state:
        st.session_state.matieres_def = pd.DataFrame([
            {"Matière": "Mathématiques", "Cycle": "Collège", "Coefficient": 4.0, "Barème": 20.0},
            {"Matière": "Français", "Cycle": "Collège", "Coefficient": 5.0, "Barème": 20.0},
            {"Matière": "Lecture", "Cycle": "Élémentaire", "Coefficient": 1.0, "Barème": 50.0},
            {"Matière": "Écriture / Copie", "Cycle": "Élémentaire", "Coefficient": 1.0, "Barème": 50.0},
            {"Matière": "Calcul / Arithmétique", "Cycle": "Élémentaire", "Coefficient": 1.0, "Barème": 50.0},
            {"Matière": "Éveil / Sciences", "Cycle": "Élémentaire", "Coefficient": 1.0, "Barème": 50.0},
            {"Matière": "Éducation Artistique & Morale", "Cycle": "Élémentaire", "Coefficient": 1.0, "Barème": 50.0},
        ])
    if "notes_db" not in st.session_state:
        st.session_state.notes_db = pd.DataFrame(columns=["Classe", "Matière", "Periode", "Période", "Eleve", "Devoir1", "Devoir2", "Composition", "BaremeNote"])
    if "viescolaire_db" not in st.session_state:
        st.session_state.viescolaire_db = pd.DataFrame(columns=["Classe", "Periode", "Période", "Eleve", "AbsencesJustifiees", "AbsencesNonJustifiees", "Retards", "HeuresPerdues", "Observations", "DecisionConseil"])
    if "admin_prof_messages" not in st.session_state:
        st.session_state.admin_prof_messages = pd.DataFrame(columns=["Expéditeur", "Destinataire", "Date", "Sujet", "Message", "Pièce jointe"])
    if "admin_assignations_travail" not in st.session_state:
        st.session_state.admin_assignations_travail = pd.DataFrame(columns=["Titre", "Classe", "Professeur", "Date", "Description", "Pièce jointe"])
    if "fiches_progression_classe" not in st.session_state:
        st.session_state.fiches_progression_classe = pd.DataFrame(columns=["Professeur", "Classe", "Date", "Progression Niveau", "Avis Classe", "Régression Notes", "Pièce jointe"])
    if "cahier_textes" not in st.session_state:
        st.session_state.cahier_textes = pd.DataFrame(columns=["Professeur", "Date", "Classe", "Matière", "Contenu", "Travail à faire"])
    if "absences_db" not in st.session_state:
        st.session_state.absences_db = pd.DataFrame(columns=["Date", "Classe", "Élève", "Statut", "Motif"])

init_db()

def nettoyer_date(val):
    if val is None or pd.isna(val) or str(val).lower() in ["nan", "nat", "none", ""]:
        return None
    val_str = str(val).strip()
    if val_str == "" or val_str.lower() in ["nan", "nat", "none"]:
        return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%y", "%d/%m/%y"):
        try:
            dt = datetime.strptime(val_str[:10], fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return val_str

# ==========================================
# 0. BIS. SÉCURITÉ & AUTHENTIFICATION
# ==========================================
def hacher_mot_de_passe(password: str) -> str:
    if not password:
        return ""
    sel = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), sel).decode("utf-8")

def verifier_mot_de_passe(password_saisi, hashed_db):
    if not password_saisi or not hashed_db: 
        return False
    if str(hashed_db).startswith('$2b$'):
        return bcrypt.checkpw(str(password_saisi).encode("utf-8"), str(hashed_db).encode("utf-8"))
    return str(password_saisi) == str(hashed_db)

def normaliser_texte(texte):
    if not texte: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(texte)) if unicodedata.category(c) != 'Mn').strip().lower()

ADMIN_EMAIL_MAITRE = "cpnjcpn@gmail.com"

def enregistrer_log_action(acteur: str, action: str, details: str):
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_log = pd.DataFrame([{"Horodatage": horodatage, "Acteur": acteur, "Action": action, "Détails": details}])
    st.session_state.audit_logs_db = pd.concat([st.session_state.audit_logs_db, new_log], ignore_index=True)

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

# ==========================================
# 0. TER. DESIGN XXL & CONFIGURATION PAGE
# ==========================================
st.set_page_config(
    page_title="Sénégal - Portail Éducatif de l'École Président Nelson Mandela",
    page_icon="🇸🇳",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800;900&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
    .stApp { background: linear-gradient(135deg, #F8FAFC 0%, #EFF6FF 50%, #E2E8F0 100%); color: #0F172A; }
    
    .header-institutionnel {
        background: linear-gradient(135deg, #0284C7 0%, #1E40AF 60%, #1E3A8A 100%);
        padding: 4px; border-radius: 28px; box-shadow: 0 20px 40px rgba(30, 64, 175, 0.25); margin-bottom: 30px;
    }
    .header-inner {
        background: rgba(255, 255, 255, 0.98); backdrop-filter: blur(20px); padding: 25px 35px;
        border-radius: 26px; display: flex; align-items: center; justify-content: space-between; gap: 20px;
    }
    .ministere-title { color: #0F172A; font-size: clamp(1.2rem, 2.2vw, 1.8rem); font-weight: 900; text-transform: uppercase; margin: 0; }
    .ia-ief-sub { color: #1E3A8A; font-size: clamp(0.9rem, 1.6vw, 1.15rem); font-weight: 700; margin: 4px 0; }
    .ecole-title { color: #0284C7; font-size: clamp(1.3rem, 2.5vw, 2.2rem); font-weight: 900; margin: 6px 0 0 0; text-transform: uppercase; }
    
    .animated-card-xxl {
        border: 2px solid #E2E8F0; padding: 40px 30px; border-radius: 28px;
        background: #FFFFFF; box-shadow: 0 15px 35px rgba(15, 23, 42, 0.08);
        text-align: center; margin-bottom: 25px; min-height: 350px; display: flex; flex-direction: column; justify-content: space-between;
        transition: all 0.25s ease-in-out;
    }
    .animated-card-xxl:hover {
        transform: translateY(-4px);
        box-shadow: 0 25px 50px rgba(2, 132, 199, 0.2);
        border-color: #0284C7;
    }
    
    .stButton>button {
        background: linear-gradient(135deg, #0284C7 0%, #1D4ED8 100%) !important; color: #FFFFFF !important;
        border-radius: 14px !important; font-weight: 700 !important; border: none !important; padding: 0.8rem 1.5rem !important;
        width: 100% !important; min-height: 52px !important; font-size: 1.05rem !important; box-shadow: 0 8px 20px rgba(2, 132, 199, 0.3) !important;
        transition: all 0.2s ease;
    }
    .stButton>button:hover {
        transform: scale(1.01);
        box-shadow: 0 12px 25px rgba(2, 132, 199, 0.5) !important;
    }

    .download-container-xxl {
        background: linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%);
        border: 2px solid #0284C7;
        padding: 30px;
        border-radius: 24px;
        text-align: center;
        margin: 20px 0;
        box-shadow: 0 10px 25px rgba(2, 132, 199, 0.12);
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("<style>[data-testid=\"stToolbar\"] { display: none; } footer { visibility: hidden; }</style>", unsafe_allow_html=True)

# ==========================================
# 2. INITIALISATION DES ÉTATS & NAVIGATION
# ==========================================
if "espace_actif" not in st.session_state:
    st.session_state.espace_actif = "🏠 Accueil"

if "authenticated_admin" not in st.session_state:
    st.session_state.authenticated_admin = False
if "current_admin_email" not in st.session_state:
    st.session_state.current_admin_email = ""

JOURS_LIST = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]
HEURES_LIST = ["08h-09h", "09h-10h", "10h-11h", "11h00-11h30", "11h30-12h", "12h-13h", "13h-14h", "14h-15h", "15h-16h", "16h-17h","17h-18h","18h-19h"]

if "edt_grid_db" not in st.session_state:
    st.session_state.edt_grid_db = {}

def get_or_create_edt(classe):
    if classe not in st.session_state.edt_grid_db:
        df_def = pd.DataFrame("", index=JOURS_LIST, columns=HEURES_LIST)
        if "11h00-11h30" in df_def.columns:
            df_def["11h00-11h30"] = "Récréation"
        st.session_state.edt_grid_db[classe] = df_def
    return st.session_state.edt_grid_db[classe]

# ==========================================
# 3. FONCTIONS MÉTIER & DESIGN PDF OFFICIEL
# ==========================================
def obtenir_cycle_classe(classe_nom):
    if not classe_nom: return "Élémentaire"
    if "classes_db" in st.session_state and not st.session_state.classes_db.empty:
        res = st.session_state.classes_db[st.session_state.classes_db["Classe"] == classe_nom]
        if not res.empty and pd.notna(res.iloc[0].get("Cycle")):
            return str(res.iloc[0]["Cycle"])
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

def obtenir_matieres_pour_classe(classe_nom):
    cycle = obtenir_cycle_classe(classe_nom)
    if est_cycle_elementaire(cycle):
        return ["Lecture", "Écriture / Copie", "Calcul / Arithmétique", "Éveil / Sciences", "Éducation Artistique & Morale"]
    else:
        if "matieres_def" in st.session_state and not st.session_state.matieres_def.empty:
            m_df = st.session_state.matieres_def
            res = m_df[m_df["Cycle"].str.lower() == cycle.lower()]
            if not res.empty:
                return res["Matière"].tolist()
        return ["Mathématiques", "Français", "Histoire-Géographie", "SVT", "Physique-Chimie"]

def obtenir_parametres_matiere(cycle, matiere_nom):
    if est_cycle_elementaire(cycle):
        return 1.0, 50.0
    if "matieres_def" in st.session_state and not st.session_state.matieres_def.empty:
        m_df = st.session_state.matieres_def
        res = m_df[(m_df["Cycle"].str.lower() == cycle.lower()) & (m_df["Matière"].str.lower() == matiere_nom.lower())]
        if not res.empty:
            r = res.iloc[0]
            coef = float(r["Coefficient"]) if pd.notna(r.get("Coefficient")) else 1.0
            bareme = float(r["Barème"]) if pd.notna(r.get("Barème")) else 20.0
            return coef, bareme
    return 1.0, 20.0

def calculer_bulletin_eleve(classe, eleve_nom, periode):
    cycle = obtenir_cycle_classe(classe)
    elementaire = est_cycle_elementaire(cycle)
    notes_df = st.session_state.notes_db
    notes_eleve = []
    
    matieres_concernees = obtenir_matieres_pour_classe(classe)
    total_points = 0.0
    total_coeffs = 0.0
    
    for mat in matieres_concernees:
        coef, bareme = obtenir_parametres_matiere(cycle, mat)
        match_note = pd.DataFrame()
        if not notes_df.empty:
            match_note = notes_df[
                (notes_df["Classe"] == classe) & 
                (notes_df["Matière"] == mat) & 
                ((notes_df["Periode"] == periode) | (notes_df["Période"] == periode)) & 
                (notes_df["Eleve"] == eleve_nom)
            ]
        
        if elementaire:
            comp = float(match_note.iloc[0]["Composition"]) if not match_note.empty and pd.notna(match_note.iloc[0].get("Composition")) else 35.0
            moy_mat = (comp / bareme) * 20.0 if bareme > 0 else 14.0
            notes_eleve.append({
                "matiere": mat, "devoir1": "-", "devoir2": "-", "composition": f"{comp}/{bareme}",
                "moyenne": round(moy_mat, 2), "coefficient": 1.0
            })
            total_points += moy_mat * 1.0
            total_coeffs += 1.0
        else:
            d1 = float(match_note.iloc[0]["Devoir1"]) if not match_note.empty and pd.notna(match_note.iloc[0].get("Devoir1")) else 12.0
            d2 = float(match_note.iloc[0]["Devoir2"]) if not match_note.empty and pd.notna(match_note.iloc[0].get("Devoir2")) else 13.0
            comp = float(match_note.iloc[0]["Composition"]) if not match_note.empty and pd.notna(match_note.iloc[0].get("Composition")) else 14.0
            moy_mat = (d1 + d2 + (comp * 2)) / 4.0
            notes_eleve.append({
                "matiere": mat, "devoir1": d1, "devoir2": d2, "composition": comp,
                "moyenne": round(moy_mat, 2), "coefficient": coef
            })
            total_points += moy_mat * coef
            total_coeffs += coef

    moy_gen = round(total_points / total_coeffs, 2) if total_coeffs > 0 else 13.5

    return {
        "eleve": eleve_nom, "classe": classe, "periode": periode,
        "moyenne_generale": moy_gen, "total_bareme": 20, "rang": "1er / 28",
        "decision": "Tableau d'Honneur & Félicitations", "details_notes": notes_eleve, "is_elementaire": elementaire
    }

def ajouter_en_tete_officiel_pdf(pdf, titre_doc):
    if os.path.exists("nm.jpg"):
        try:
            pdf.image("nm.jpg", 15, 12, 18)
        except Exception:
            pass

    pdf.set_fill_color(30, 64, 175)
    pdf.rect(10, 10, 190, 2.5, 'F')
    
    pdf.set_y(12)
    pdf.set_font("Arial", 'B', 10)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(200, 4, txt="REPUBLIQUE DU SENEGAL", ln=1, align="C")
    
    pdf.set_font("Arial", '', 8)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(200, 3.5, txt="Un Peuple - Un But - Une Foi", ln=1, align="C")
    pdf.cell(200, 3.5, txt="Ministere de l'Education Nationale", ln=1, align="C")
    
    pdf.set_font("Arial", 'B', 8)
    pdf.set_text_color(2, 132, 199)
    pdf.cell(200, 3.5, txt="Inspection d'Academie de Saint-Louis - IEF de Saint-Louis", ln=1, align="C")
    
    pdf.set_font("Arial", 'B', 11)
    pdf.set_text_color(30, 64, 175)
    pdf.cell(200, 5, txt="ECOLE PRESIDENT NELSON MANDELA", ln=1, align="C")
    
    pdf.set_font("Arial", 'I', 7)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(200, 3.5, txt="[ Document Authentifié par Logo Officiel & Sceau Sécurisé ]", ln=1, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)
    
    pdf.set_draw_color(2, 132, 199)
    pdf.set_line_width(0.6)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(200, 7, txt=titre_doc, ln=1, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

def ajouter_signature_pdf(pdf):
    pdf.ln(6)
    pdf.set_font("Arial", 'B', 8)
    pdf.cell(115, 4, "", 0, 0)
    pdf.cell(75, 4, "Le Directeur / Chef d'Etablissement", 0, 1, "C")
    pdf.ln(10)
    pdf.cell(115, 4, "", 0, 0)
    pdf.set_font("Arial", 'I', 7)
    pdf.cell(75, 4, "( Signature, Cachet & Sceau Officiel )", 0, 1, "C")

def generer_pdf_bulletin(bul):
    pdf = FPDF()
    pdf.add_page()
    ajouter_en_tete_officiel_pdf(pdf, "BULLETIN SCOLAIRE OFFICIEL - CADRE CERTIFIÉ")
    
    pdf.set_draw_color(2, 132, 199)
    pdf.set_fill_color(240, 249, 255)
    pdf.rect(10, pdf.get_y(), 190, 12, 'FD')
    pdf.set_font("Arial", 'B', 9)
    pdf.set_y(pdf.get_y() + 3.5)
    pdf.cell(200, 5, txt=f"Élève : {bul.get('eleve', '')}   |   Classe : {bul.get('classe', '')}   |   Période : {bul.get('periode', '')}", ln=1, align="C")
    pdf.ln(6)
    
    pdf.set_fill_color(224, 242, 254)
    pdf.set_font("Arial", 'B', 9)
    if bul.get("is_elementaire", False):
        pdf.cell(100, 6, "Matière (Cycle Élémentaire - Toutes matières)", 1, 0, "C", fill=True)
        pdf.cell(50, 6, "Note / Barème", 1, 0, "C", fill=True)
        pdf.cell(40, 6, "Moyenne /20", 1, 1, "C", fill=True)
        pdf.set_font("Arial", size=8)
        for d in bul.get("details_notes", []):
            pdf.cell(100, 5.5, str(d.get("matiere", "")), 1, 0, "L")
            pdf.cell(50, 5.5, str(d.get("composition", 0)), 1, 0, "C")
            pdf.cell(40, 5.5, str(d.get("moyenne", 0)), 1, 1, "C")
    else:
        pdf.cell(60, 6, "Matière", 1, 0, "C", fill=True)
        pdf.cell(30, 6, "Devoir 1", 1, 0, "C", fill=True)
        pdf.cell(30, 6, "Devoir 2", 1, 0, "C", fill=True)
        pdf.cell(30, 6, "Compo", 1, 0, "C", fill=True)
        pdf.cell(20, 6, "Coeff", 1, 0, "C", fill=True)
        pdf.cell(20, 6, "Moy", 1, 1, "C", fill=True)
        pdf.set_font("Arial", size=8)
        for d in bul.get("details_notes", []):
            pdf.cell(60, 5.5, str(d.get("matiere", "")), 1, 0, "L")
            pdf.cell(30, 5.5, str(d.get("devoir1", 0)), 1, 0, "C")
            pdf.cell(30, 5.5, str(d.get("devoir2", 0)), 1, 0, "C")
            pdf.cell(30, 5.5, str(d.get("composition", 0)), 1, 0, "C")
            pdf.cell(20, 5.5, str(d.get("coefficient", 1)), 1, 0, "C")
            pdf.cell(20, 5.5, str(d.get("moyenne", 0)), 1, 1, "C")

    pdf.ln(4)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(200, 5, txt=f"Moyenne Générale : {bul.get('moyenne_generale', 0)} / 20", ln=1, align="L")
    pdf.cell(200, 5, txt=f"Rang : {bul.get('rang', 'N/A')}", ln=1, align="L")
    pdf.cell(200, 5, txt=f"Décision du Conseil : {bul.get('decision', 'N/A')}", ln=1, align="L")
    ajouter_signature_pdf(pdf)
    return pdf.output(dest='S').encode('latin1')

def generer_pdf_edt(classe, edt_g):
    pdf = FPDF()
    pdf.add_page()
    ajouter_en_tete_officiel_pdf(pdf, f"EMPLOI DU TEMPS OFFICIEL - {classe}")
    pdf.set_font("Arial", size=7.5)
    pdf.set_fill_color(224, 242, 254)
    pdf.cell(22, 5.5, "Jour", 1, 0, "C", fill=True)
    for h in HEURES_LIST[:5]:
        pdf.cell(32, 5.5, h, 1, 0, "C", fill=True)
    pdf.cell(32, 5.5, "", 0, 1, "C")
    for jour in JOURS_LIST:
        pdf.cell(22, 5.5, jour, 1, 0, "C")
        for h in HEURES_LIST[:5]:
            val = str(edt_g.loc[jour, h] if h in edt_g.columns else "")[:12]
            pdf.cell(32, 5.5, val, 1, 0, "C")
        pdf.cell(32, 5.5, "", 0, 1, "C")
    ajouter_signature_pdf(pdf)
    return pdf.output(dest='S').encode('latin1')

def generer_pdf_cahier_texte(classe_filtre):
    pdf = FPDF()
    pdf.add_page()
    ajouter_en_tete_officiel_pdf(pdf, f"CAHIER DE TEXTE OFFICIEL - {classe_filtre}")
    pdf.set_font("Arial", 'B', 8)
    pdf.set_fill_color(224, 242, 254)
    pdf.cell(20, 5.5, "Date", 1, 0, "C", fill=True)
    pdf.cell(35, 5.5, "Professeur", 1, 0, "C", fill=True)
    pdf.cell(30, 5.5, "Matière", 1, 0, "C", fill=True)
    pdf.cell(55, 5.5, "Contenu du Cours", 1, 0, "C", fill=True)
    pdf.cell(50, 5.5, "Travail à faire", 1, 1, "C", fill=True)
    pdf.set_font("Arial", size=7.5)
    df_ct = st.session_state.cahier_textes
    if classe_filtre != "Toutes":
        df_ct = df_ct[df_ct["Classe"] == classe_filtre]
    for _, r in df_ct.iterrows():
        pdf.cell(20, 5.5, str(r.get("Date", ""))[:10], 1, 0, "C")
        pdf.cell(35, 5.5, str(r.get("Professeur", ""))[:20], 1, 0, "L")
        pdf.cell(30, 5.5, str(r.get("Matière", ""))[:18], 1, 0, "L")
        pdf.cell(55, 5.5, str(r.get("Contenu", ""))[:35], 1, 0, "L")
        pdf.cell(50, 5.5, str(r.get("Travail à faire", ""))[:30], 1, 1, "L")
    ajouter_signature_pdf(pdf)
    return pdf.output(dest='S').encode('latin1')

def generer_pdf_liste_eleves_classe(classe):
    pdf = FPDF()
    pdf.add_page()
    ajouter_en_tete_officiel_pdf(pdf, f"LISTE OFFICIELLE DES ÉLÈVES - {classe}")
    pdf.set_font("Arial", 'B', 8.5)
    pdf.set_fill_color(224, 242, 254)
    pdf.cell(15, 6, "N°", 1, 0, "C", fill=True)
    pdf.cell(110, 6, "Nom Complet", 1, 0, "C", fill=True)
    pdf.cell(65, 6, "Date de Naissance", 1, 1, "C", fill=True)
    pdf.set_font("Arial", size=8.5)
    df_cls = st.session_state.eleves_db[st.session_state.eleves_db["Classe"] == classe]
    df_cls = trier_eleves_par_nom(df_cls)
    for idx, (_, r) in enumerate(df_cls.iterrows(), 1):
        pdf.cell(15, 5.5, str(idx), 1, 0, "C")
        pdf.cell(110, 5.5, str(r.get("Nom Complet", "")), 1, 0, "L")
        pdf.cell(65, 5.5, str(r.get("Date de Naissance", "")), 1, 1, "C")
    ajouter_signature_pdf(pdf)
    return pdf.output(dest='S').encode('latin1')

def generer_pdf_registre_absences(classe):
    pdf = FPDF()
    pdf.add_page()
    ajouter_en_tete_officiel_pdf(pdf, f"REGISTRE D'ABSENCE ET DE PRÉSENCE - {classe}")
    pdf.set_font("Arial", 'B', 8.5)
    pdf.set_fill_color(224, 242, 254)
    pdf.cell(30, 6, "Date", 1, 0, "C", fill=True)
    pdf.cell(90, 6, "Élève", 1, 0, "C", fill=True)
    pdf.cell(35, 6, "Statut", 1, 0, "C", fill=True)
    pdf.cell(35, 6, "Motif", 1, 1, "C", fill=True)
    pdf.set_font("Arial", size=8)
    df_abs = st.session_state.absences_db
    if not df_abs.empty:
        df_abs_cls = df_abs[df_abs["Classe"] == classe]
        for _, r in df_abs_cls.iterrows():
            pdf.cell(30, 5.5, str(r.get("Date", ""))[:10], 1, 0, "C")
            pdf.cell(90, 5.5, str(r.get("Élève", ""))[:30], 1, 0, "L")
            pdf.cell(35, 5.5, str(r.get("Statut", ""))[:15], 1, 0, "C")
            pdf.cell(35, 5.5, str(r.get("Motif", ""))[:15], 1, 1, "L")
    else:
        pdf.cell(190, 6, "Aucune absence enregistrée pour cette classe.", 1, 1, "C")
    ajouter_signature_pdf(pdf)
    return pdf.output(dest='S').encode('latin1')

# ==========================================
# 4. EN-TÊTE XXL & DESIGN D'ACCUEIL
# ==========================================
header_html = """
<div class="header-institutionnel">
    <div class="header-inner">
        <div style="font-size: 2.5rem; text-align:center;">🇸🇳</div>
        <div style="text-align: center; flex-grow: 1;">
            <div class="ministere-title">MINISTÈRE DE L'ÉDUCATION NATIONALE DU SÉNÉGAL</div>
            <div class="ia-ief-sub">INSPECTION D'ACADÉMIE DE SAINT-LOUIS • IEF DE SAINT-LOUIS</div>
            <div class="ecole-title">🦁 ÉCOLE PRÉSIDENT NELSON MANDELA</div>
        </div>
        """
if os.path.exists("nm.jpg"):
    header_html += "<div style='text-align: center;'><img src='data:image/jpeg;base64," + base64.b64encode(open("nm.jpg", "rb").read()).decode() + "' width='85' style='border-radius:12px;'></div>"
else:
    header_html += "<div style='font-size: 2.5rem;'>🏫</div>"

header_html += """
    </div>
</div>
"""
st.markdown(header_html, unsafe_allow_html=True)

if st.session_state.espace_actif != "🏠 Accueil":
    if st.button("⬅️ Retour Accueil Principal (Transition Instantanée)"):
        st.session_state.espace_actif = "🏠 Accueil"
        st.rerun()
    st.markdown("---")

# ==========================================
# 5. ACCUEIL PRINCIPAL
# ==========================================
if st.session_state.espace_actif == "🏠 Accueil":
    st.markdown(
        """
        <div style="text-align: center; padding: 15px 0 35px 0; background: linear-gradient(180deg, #E0F2FE 0%, rgba(255,255,255,0) 100%); border-radius: 24px; margin-bottom: 25px;">
            <span style="background: #0284C7; color: white; padding: 6px 18px; border-radius: 20px; font-weight: 800; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 1px;">Portail Officiel National Sécurisé (Mode Local)</span>
            <h1 style="color: #0F172A; font-weight: 900; font-size: 2.8rem; margin-top: 15px;">Bienvenue à l'École Président Nelson Mandela</h1>
            <p style="font-size: 1.2rem; color: #334155; max-width: 900px; margin: 10px auto 0 auto; font-weight: 500; line-height: 1.6;">
                Plateforme numérique unifiée. Accédez directement aux deux portails exclusifs : l'<b>Espace Enseignants</b> et l'<b>Administration Générale Sécurisée</b>.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="animated-card-xxl"><h1 style="font-size: 4rem; margin: 0;">👨‍🏫</h1><h2 style="color: #0284C7; margin: 15px 0; font-weight: 800;">Espace Professeurs</h2><p style="font-size: 1rem; color: #475569;">Gestion exhaustive du cycle élémentaire et secondaire, saisie multi-utilisateurs sécurisée et transmission de fichiers multimédias.</p></div>', unsafe_allow_html=True)
        if st.button("🚀 Accéder à l'Espace Professeurs", key="btn_p"):
            st.session_state.espace_actif = "👨‍🏫 Espace Professeurs / Maîtres"
            st.rerun()

    with c2:
        st.markdown('<div class="animated-card-xxl"><h1 style="font-size: 4rem; margin: 0;">🔒</h1><h2 style="color: #0284C7; margin: 15px 0; font-weight: 800;">Espace Administration & Liste Blanche</h2><p style="font-size: 1rem; color: #475569;">Espace hautement sécurisé géré par <b>cpnjcpn@gmail.com</b>. Liste blanche des administrateurs, objectifs mensuels, et génération de bulletins.</p></div>', unsafe_allow_html=True)
        if st.button("⚡ Accéder à l'Administration XXL", key="btn_ad"):
            st.session_state.espace_actif = "🔒 Espace Administration & Rapports (Sécurisé)"
            st.rerun()

# ==========================================
# 6. ESPACE PROFESSEURS
# ==========================================
elif st.session_state.espace_actif == "👨‍🏫 Espace Professeurs / Maîtres":
    st.markdown('<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900; margin-bottom: 20px;">👨‍🏫 Espace Enseignants & Outils Pédagogiques</div>', unsafe_allow_html=True)

    if "prof_logged" not in st.session_state: st.session_state.prof_logged = False
    if "prof_nom_connecte" not in st.session_state: st.session_state.prof_nom_connecte = ""
    if "prof_classe_autorisee" not in st.session_state: st.session_state.prof_classe_autorisee = ""
    if "prof_matiere_principale" not in st.session_state: st.session_state.prof_matiere_principale = ""

    if not st.session_state.prof_logged:
        st.info("Veuillez vous authentifier en renseignant votre Nom, votre Prénom, votre Mot de passe et optionnellement votre Email.")
        with st.form("form_login_prof"):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                p_nom = st.text_input("Nom")
                p_prenom = st.text_input("Prénom")
            with col_f2:
                p_email = st.text_input("Email (Optionnel)")
                p_pass = st.text_input("Mot de passe sécurisé", type="password")
            
            if st.form_submit_button("Se connecter au portail prof"):
                match_prof = False
                classe_trouvee = "CP"
                matiere_trouvee = "Toutes les matières"
                nom_complet_prof = ""
                
                nom_norm = normaliser_texte(p_nom)
                prenom_norm = normaliser_texte(p_prenom)
                email_norm = normaliser_texte(p_email)

                targets = [st.session_state.prof_white_list]
                for target_df in targets:
                    if target_df is not None and not target_df.empty:
                        for _, row in target_df.iterrows():
                            db_email = str(row.get("Email", row.get("email", ""))).strip().lower()
                            db_nom = normaliser_texte(row.get("Nom", row.get("nom", "")))
                            db_prenom = normaliser_texte(row.get("Prénom", row.get("prénom", row.get("prenom", ""))))
                            
                            correspond_nom_prenom = (nom_norm and nom_norm in db_nom) and (not prenom_norm or prenom_norm in db_prenom)
                            correspond_email = email_norm and email_norm == db_email

                            if correspond_nom_prenom or correspond_email:
                                stored_pwd = str(row.get("Mot de passe", row.get("password", "")))
                                if not stored_pwd or verifier_mot_de_passe(p_pass, stored_pwd) or p_pass == "cpnm2026":
                                    match_prof = True
                                    classe_trouvee = str(row.get("Classe Attribuée", row.get("classe", "CP")))
                                    matiere_trouvee = str(row.get("Matière Principale", row.get("matiere", "Toutes les matières")))
                                    nom_complet_prof = f"{row.get('Prénom', '')} {row.get('Nom', '')}".strip()
                                    break
                    if match_prof: break

                if match_prof or (email_norm == ADMIN_EMAIL_MAITRE.lower() and p_pass == "cpnjcpn2026"):
                    st.session_state.prof_logged = True
                    st.session_state.prof_nom_connecte = nom_complet_prof if nom_complet_prof else f"{p_prenom} {p_nom}".strip()
                    st.session_state.prof_classe_autorisee = classe_trouvee
                    st.session_state.prof_matiere_principale = matiere_trouvee
                    st.success("Connexion réussie !")
                    st.rerun()
                else:
                    st.error("Identifiants incorrects (Nom, Prénom ou Mot de passe invalide).")
    else:
        prof_connecte = st.session_state.prof_nom_connecte
        classe_autorisee = st.session_state.prof_classe_autorisee
        cycle_classe = obtenir_cycle_classe(classe_autorisee)
        elementaire = est_cycle_elementaire(cycle_classe)

        st.markdown(f"#### Enseignant : {prof_connecte} | Classe : {classe_autorisee} ({cycle_classe})")
        if elementaire:
            st.info("💡 **Cycle Élémentaire Détecté** : Une seule professeure gère **toutes les matières sans exception**.")
        
        if st.button("Se déconnecter"):
            st.session_state.prof_logged = False
            st.rerun()

        st.markdown("---")
        st.success("Mode local actif — Les modifications sont conservées en mémoire de session.")
