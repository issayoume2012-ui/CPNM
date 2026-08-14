# --- BIBLIOTHÈQUES STANDARDS & DÉPENDANCES ---
import base64
from datetime import datetime
import io
import os
import zipfile
import unicodedata
import numpy as np
import pandas as pd
from fpdf import FPDF
import streamlit as st
import bcrypt
from supabase import create_client, Client

# --- CONFIGURATION & CONNEXION SUPABASE ---
# L'URL exacte du projet Supabase
DEFAULT_URL = "https://gxzprzrufqvblwoyqihd.supabase.co"
DEFAULT_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd4enByenR1ZnF2Ymx3b3lxaWhkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2NTAwNDgsImV4cCI6MjEwMjIyNjA0OH0.CK9c_hb3bp6q0V7zHBWoX15BwqNHCUSYY9DRXqgOP_Q"

try:
    SUPABASE_URL = st.secrets["supabase"]["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["supabase"]["SUPABASE_KEY"]
except Exception:
    SUPABASE_URL = DEFAULT_URL
    SUPABASE_KEY = DEFAULT_KEY

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- INITIALISATION ET SYNCHRONISATION SUPABASE / SESSION STATE ---

def charger_table_supabase(table_name: str, cols_mapping: dict = None) -> pd.DataFrame:
    try:
        res = supabase.table(table_name).select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty and cols_mapping:
            df = df.rename(columns=cols_mapping)
        return df
    except Exception as e:
        return pd.DataFrame()

# Chargement de la liste blanche parents depuis Supabase
if "parents_white_list" not in st.session_state:
    df_p = charger_table_supabase("parents_white_list", {
        "telephone": "Téléphone",
        "prenom_eleve": "Prénom Élève",
        "nom_eleve": "Nom Élève",
        "classe": "Classe"
    })
    if df_p.empty:
        st.session_state.parents_white_list = pd.DataFrame([
            {
                "Téléphone": "771234567",
                "Prénom Élève": "Issa",
                "Nom Élève": "",
                "Classe": "6ème A"
            }
        ])
    else:
        st.session_state.parents_white_list = df_p

# Chargement des élèves depuis Supabase
if "eleves_db" not in st.session_state:
    df_e = charger_table_supabase("eleves", {
        "nom_complet": "Nom Complet",
        "nom": "Nom",
        "prenom": "Prénom",
        "classe": "Classe"
    })
    if df_e.empty:
        st.session_state.eleves_db = pd.DataFrame([
            {
                "Nom Complet": "Issa",
                "Nom": "Issa",
                "Prénom": "",
                "Classe": "6ème A"
            }
        ])
    else:
        st.session_state.eleves_db = df_e

# Chargement des messages parents depuis Supabase
if "messages_parents_db" not in st.session_state:
    df_m = charger_table_supabase("messages_parents", {
        "id": "ID",
        "emetteur": "Emetteur",
        "role_emetteur": "RoleEmetteur",
        "date_envoi": "DateEnvoi",
        "classe": "Classe",
        "objet": "Objet",
        "message": "Message",
        "urgent": "Urgent"
    })
    if df_m.empty:
        st.session_state.messages_parents_db = pd.DataFrame(columns=[
            "ID", "Emetteur", "RoleEmetteur", "DateEnvoi", "Classe", "Objet", "Message", "Urgent"
        ])
    else:
        st.session_state.messages_parents_db = df_m

# Chargement du travail à faire depuis Supabase
if "travail_a_faire_db" not in st.session_state:
    df_taf = charger_table_supabase("travail_a_faire", {
        "id": "ID",
        "titre": "Titre",
        "matiere": "Matière",
        "classe": "Classe",
        "professeur": "Professeur",
        "date_rendu": "DateRendu",
        "consignes": "Consignes",
        "lien_url": "LienUrl",
        "lien_video": "LienVideo",
        "fichier_b64": "FichierB64",
        "fichier_nom": "FichierNom"
    })
    st.session_state.travail_a_faire_db = df_taf

# Chargement des notes depuis Supabase
if "notes_db" not in st.session_state:
    df_n = charger_table_supabase("notes", {
        "classe": "Classe",
        "periode": "Periode",
        "eleve": "Eleve",
        "matiere": "Matière",
        "devoir1": "Devoir1",
        "devoir2": "Devoir2",
        "composition": "Composition"
    })
    st.session_state.notes_db = df_n

# Chargement de la vie scolaire depuis Supabase
if "viescolaire_db" not in st.session_state:
    df_vs = charger_table_supabase("vie_scolaire", {
        "classe": "Classe",
        "periode": "Periode",
        "eleve": "Eleve",
        "absences_justifiees": "AbsencesJustifiees",
        "absences_non_justifiees": "AbsencesNonJustifiees",
        "retards": "Retards",
        "heures_perdues": "HeuresPerdues",
        "observations": "Observations",
        "decision_conseil": "DecisionConseil"
    })
    st.session_state.viescolaire_db = df_vs

# Chargement des classes depuis Supabase
if "classes_db" not in st.session_state:
    df_cls = charger_table_supabase("classes", {
        "classe": "Classe",
        "cycle": "Cycle"
    })
    st.session_state.classes_db = df_cls

# Chargement des périodes depuis Supabase
if "periodes_db" not in st.session_state:
    df_per = charger_table_supabase("periodes", {
        "periode": "Période",
        "cycle": "Cycle"
    })
    st.session_state.periodes_db = df_per

# Chargement des coefficients depuis Supabase
if "coefficients_db" not in st.session_state:
    df_coef = charger_table_supabase("coefficients", {
        "classe": "Classe",
        "matiere": "Matière",
        "coefficient": "Coefficient",
        "bareme": "Barème"
    })
    st.session_state.coefficients_db = df_coef

# Chargement des matières par défaut depuis Supabase
if "matieres_def" not in st.session_state:
    df_mat = charger_table_supabase("matieres", {
        "matiere": "Matière",
        "cycle": "Cycle",
        "coefficient": "Coefficient",
        "bareme": "Barème"
    })
    st.session_state.matieres_def = df_mat


# --- FONCTIONS UTILITAIRES DE BASE ---
def normaliser_texte(texte):
    if not texte: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(texte)) if unicodedata.category(c) != 'Mn').strip().lower()

def nettoyer_texte_pdf(texte):
    if not texte: return ""
    return str(texte).encode('latin-1', 'replace').decode('latin-1')

ADMIN_EMAIL = "cpnm@gmail.com"

def trier_eleves_par_nom(df):
    if df is None or df.empty: return df
    df_copy = df.copy()
    if "Nom" in df_copy.columns and "Prénom" in df_copy.columns:
        df_copy["Nom_Sort"] = df_copy["Nom"].astype(str).str.strip().str.upper()
        df_copy["Prenom_Sort"] = df_copy["Prénom"].astype(str).str.strip().str.upper()
        df_copy = df_copy.sort_values(by=["Nom_Sort", "Prenom_Sort"]).drop(columns=["Nom_Sort", "Prenom_Sort"])
    return df_copy.reset_index(drop=True)

def obtenir_cycle_classe(classe_nom):
    if not classe_nom: return "Élémentaire"
    classe_str = str(classe_nom).strip()
    if "classes_db" in st.session_state and not st.session_state.classes_db.empty and "Classe" in st.session_state.classes_db.columns:
        res = st.session_state.classes_db[st.session_state.classes_db["Classe"].str.strip().str.upper() == classe_str.upper()]
        if not res.empty and pd.notna(res.iloc[0].get("Cycle")):
            return str(res.iloc[0]["Cycle"]).strip()
    classe_clean = classe_str.upper()
    if any(c in classe_clean for c in ["6ÈME", "6EME", "5ÈME", "5EME", "4ÈME", "4EME", "3ÈME", "3EME", "COLLÈGE", "COLLEGE"]):
        return "Collège"
    if any(classe_clean.startswith(prefix) for prefix in ["CI", "CP", "CE1", "CE2", "CM1", "CM2", "ÉLÉMENTAIRE", "ELEMENTAIRE"]):
        return "Élémentaire"
    return "Élémentaire"

def est_cycle_elementaire(cycle_or_classe):
    if not cycle_or_classe: return True
    val = str(cycle_or_classe).strip().lower()
    if "élément" in val or "element" in val: return True
    if "collèg" in val or "colleg" in val: return False
    return est_cycle_elementaire(obtenir_cycle_classe(cycle_or_classe))

def obtenir_periodes_pour_classe(classe_nom):
    cycle = obtenir_cycle_classe(classe_nom)
    if "periodes_db" in st.session_state and not st.session_state.periodes_db.empty:
        df_p = st.session_state.periodes_db
        col_cycle = "Cycle" if "Cycle" in df_p.columns else None
        col_periode = "Période" if "Période" in df_p.columns else ("Periode" if "Periode" in df_p.columns else None)
        if col_cycle and col_periode:
            filtre = df_p[df_p[col_cycle].apply(est_cycle_elementaire) == est_cycle_elementaire(cycle)][col_periode].dropna().tolist()
            if filtre: return filtre
        elif col_periode:
            return df_p[col_periode].dropna().tolist()
    if est_cycle_elementaire(cycle):
        return ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"]
    else:
        return ["1er Semestre", "2ème Semestre"]

def obtenir_appreciation(moyenne, cycle="Collège", bareme=20):
    if pd.isna(moyenne): return "N/A"
    m = (moyenne / bareme) * 20.0 if bareme > 0 else moyenne
    if m >= 18: return "Excellent"
    elif m >= 16: return "Très Bien"
    elif m >= 14: return "Bien"
    elif m >= 12: return "Assez Bien"
    elif m >= 10: return "Passable"
    elif m >= 8: return "Insuffisant"
    else: return "Faible"

def obtenir_coefficient_matiere(classe, matiere):
    if "coefficients_db" in st.session_state and not st.session_state.coefficients_db.empty:
        c_db = st.session_state.coefficients_db
        if "Classe" in c_db.columns and "Matière" in c_db.columns:
            res = c_db[(c_db["Classe"] == classe) & (c_db["Matière"] == matiere)]
            if not res.empty and pd.notna(res.iloc[0].get("Coefficient")):
                return float(res.iloc[0]["Coefficient"])
    cycle_classe = obtenir_cycle_classe(classe)
    if "matieres_def" in st.session_state and not st.session_state.matieres_def.empty:
        m_def = st.session_state.matieres_def
        if "Cycle" in m_def.columns:
            res = m_def[(m_def["Matière"] == matiere) & (m_def["Cycle"].apply(est_cycle_elementaire) == est_cycle_elementaire(cycle_classe))]
        else:
            res = m_def[m_def["Matière"] == matiere]
        if not res.empty and "Coefficient" in m_def.columns and pd.notna(res.iloc[0].get("Coefficient")):
            return float(res.iloc[0]["Coefficient"])
    return 1.0

def obtenir_bareme_matiere(classe, matiere):
    if "coefficients_db" in st.session_state and not st.session_state.coefficients_db.empty:
        c_db = st.session_state.coefficients_db
        if "Classe" in c_db.columns and "Matière" in c_db.columns:
            res = c_db[(c_db["Classe"] == classe) & (c_db["Matière"] == matiere)]
            if not res.empty and "Barème" in res.columns and pd.notna(res.iloc[0].get("Barème")):
                return float(res.iloc[0]["Barème"])
    cycle_classe = obtenir_cycle_classe(classe)
    if "matieres_def" in st.session_state and not st.session_state.matieres_def.empty:
        m_def = st.session_state.matieres_def
        if "Cycle" in m_def.columns:
            res = m_def[(m_def["Matière"] == matiere) & (m_def["Cycle"].apply(est_cycle_elementaire) == est_cycle_elementaire(cycle_classe))]
        else:
            res = m_def[m_def["Matière"] == matiere]
        if not res.empty and "Barème" in m_def.columns and pd.notna(res.iloc[0].get("Barème")):
            return float(res.iloc[0]["Barème"])
    return 50.0 if est_cycle_elementaire(cycle_classe) else 20.0

def calculer_bulletin_eleve(classe, eleve, periode):
    cycle_classe = obtenir_cycle_classe(classe)
    is_elem = est_cycle_elementaire(cycle_classe)
    matieres_set = set()
    if "coefficients_db" in st.session_state and not st.session_state.coefficients_db.empty and "Classe" in st.session_state.coefficients_db.columns:
        c_db = st.session_state.coefficients_db
        m_c = c_db[c_db["Classe"] == classe]["Matière"].dropna().tolist()
        matieres_set.update(m_c)
    if "matieres_def" in st.session_state and not st.session_state.matieres_def.empty:
        m_def = st.session_state.matieres_def
        if "Cycle" in m_def.columns:
            m_c_def = m_def[m_def["Cycle"].apply(est_cycle_elementaire) == is_elem]["Matière"].dropna().tolist()
            matieres_set.update(m_c_def)
        else:
            matieres_set.update(m_def["Matière"].dropna().tolist())
    notes_df = st.session_state.notes_db if "notes_db" in st.session_state else pd.DataFrame()
    if not notes_df.empty and "Classe" in notes_df.columns:
        cond_cls = notes_df["Classe"] == classe
        cond_per = (notes_df["Periode"] == periode) if "Periode" in notes_df.columns else ((notes_df["Période"] == periode) if "Période" in notes_df.columns else True)
        m_notes = notes_df[cond_cls & cond_per]["Matière"].dropna().unique().tolist()
        matieres_set.update(m_notes)
    if not matieres_set:
        matieres_set = {"Lecture / Langage", "Calcul / Mathématiques"} if is_elem else {"Mathématiques", "Français"}
    liste_matieres = sorted(list(matieres_set))
    notes_classe_periode = pd.DataFrame()
    if not notes_df.empty and "Classe" in notes_df.columns:
        if "Periode" in notes_df.columns:
            notes_classe_periode = notes_df[(notes_df["Classe"] == classe) & (notes_df["Periode"] == periode)]
        elif "Période" in notes_df.columns:
            notes_classe_periode = notes_df[(notes_df["Classe"] == classe) & (notes_df["Période"] == periode)]

    lignes_bulletin, total_points_global, total_coefficients_global, total_bareme_global = [], 0.0, 0.0, 0.0
    coeffs_dict = {mat: obtenir_coefficient_matiere(classe, mat) for mat in liste_matieres}
    baremes_dict = {mat: obtenir_bareme_matiere(classe, mat) for mat in liste_matieres}

    for mat in liste_matieres:
        coef = coeffs_dict.get(mat, 1.0)
        bareme_m = baremes_dict.get(mat, 50.0 if is_elem else 20.0)
        note_row = notes_classe_periode[notes_classe_periode["Eleve"] == eleve] if not notes_classe_periode.empty and "Eleve" in notes_classe_periode.columns else pd.DataFrame()
        note_mat = note_row[note_row["Matière"] == mat] if not note_row.empty and "Matière" in note_row.columns else pd.DataFrame()
        d1, d2, comp = 0.0, 0.0, 0.0
        if not note_mat.empty:
            d1 = float(note_mat.iloc[0]["Devoir1"]) if "Devoir1" in note_mat.columns and pd.notna(note_mat.iloc[0]["Devoir1"]) else 0.0
            d2 = float(note_mat.iloc[0]["Devoir2"]) if "Devoir2" in note_mat.columns and pd.notna(note_mat.iloc[0]["Devoir2"]) else 0.0
            comp = float(note_mat.iloc[0]["Composition"]) if "Composition" in note_mat.columns and pd.notna(note_mat.iloc[0]["Composition"]) else 0.0
        if is_elem:
            moy_matiere = comp
            total_points_global += moy_matiere
            total_bareme_global += bareme_m
            lignes_bulletin.append({"Matiere": mat, "Bareme": bareme_m, "Composition": comp, "MoyenneMatiere": round(moy_matiere, 2), "Appreciation": obtenir_appreciation(moy_matiere, cycle_classe, bareme_m)})
        else:
            moy_devoirs = (d1 + d2) / 2.0
            moy_matiere = (moy_devoirs + comp) / 2.0
            total_pondere = moy_matiere * coef
            total_points_global += total_pondere
            total_coefficients_global += coef
            lignes_bulletin.append({"Matiere": mat, "Coefficient": coef, "Devoir1": d1, "Devoir2": d2, "Composition": comp, "MoyenneMatiere": round(moy_matiere, 2), "TotalPondere": round(total_pondere, 2), "Appreciation": obtenir_appreciation(moy_matiere, cycle_classe, 20.0)})

    if is_elem:
        moyenne_generale = round((total_points_global / total_bareme_global) * 10.0, 2) if total_bareme_global > 0 else 0.0
    else:
        moyenne_generale = round(total_points_global / total_coefficients_global, 2) if total_coefficients_global > 0 else 0.0

    tous_eleves = []
    if "eleves_db" in st.session_state and not st.session_state.eleves_db.empty and "Classe" in st.session_state.eleves_db.columns:
        df_sorted_el = trier_eleves_par_nom(st.session_state.eleves_db[st.session_state.eleves_db["Classe"] == classe])
        tous_eleves = df_sorted_el["Nom Complet"].tolist()

    moyennes_classe = {}
    for el in tous_eleves:
        pts, coefs, bareme_tot_el = 0.0, 0.0, 0.0
        notes_el_p = notes_classe_periode[notes_classe_periode["Eleve"] == el] if not notes_classe_periode.empty and "Eleve" in notes_classe_periode.columns else pd.DataFrame()
        for mat in liste_matieres:
            coef = coeffs_dict.get(mat, 1.0)
            bareme_m = baremes_dict.get(mat, 50.0 if is_elem else 20.0)
            n_m = notes_el_p[notes_el_p["Matière"] == mat] if not notes_el_p.empty and "Matière" in notes_el_p.columns else pd.DataFrame()
            if not n_m.empty:
                d1 = float(n_m.iloc[0]["Devoir1"]) if "Devoir1" in n_m.columns and pd.notna(n_m.iloc[0]["Devoir1"]) else 0.0
                d2 = float(n_m.iloc[0]["Devoir2"]) if "Devoir2" in n_m.columns and pd.notna(n_m.iloc[0]["Devoir2"]) else 0.0
                comp = float(n_m.iloc[0]["Composition"]) if "Composition" in n_m.columns and pd.notna(n_m.iloc[0]["Composition"]) else 0.0
                if is_elem:
                    pts += comp
                    bareme_tot_el += bareme_m
                else:
                    m_mat = ((d1 + d2) / 2.0 + comp) / 2.0
                    pts += m_mat * coef
                    coefs += coef
        if is_elem:
            moyennes_classe[el] = round((pts / bareme_tot_el) * 10.0, 2) if bareme_tot_el > 0 else 0.0
        else:
            moyennes_classe[el] = round(pts / coefs, 2) if coefs > 0 else 0.0

    classement_trie = sorted(moyennes_classe.items(), key=lambda x: x[1], reverse=True)
    rang = "-"
    for idx, (el_nom, _) in enumerate(classement_trie, 1):
        if el_nom == eleve:
            rang = f"{idx} / {len(tous_eleves)}"
            break

    vs_df = st.session_state.viescolaire_db if "viescolaire_db" in st.session_state else pd.DataFrame()
    vs_row = pd.DataFrame()
    if not vs_df.empty and "Classe" in vs_df.columns and "Eleve" in vs_df.columns:
        cond_p = (vs_df["Periode"] == periode) if "Periode" in vs_df.columns else (vs_df["Période"] == periode)
        vs_row = vs_df[(vs_df["Classe"] == classe) & cond_p & (vs_df["Eleve"] == eleve)]

    abs_just, abs_non_just, retards, heures_p, obs, decision = 0, 0, 0, 0, "RAS", "Encouragements"
    if not vs_row.empty:
        abs_just = int(vs_row.iloc[0]["AbsencesJustifiees"]) if "AbsencesJustifiees" in vs_row.columns and pd.notna(vs_row.iloc[0]["AbsencesJustifiees"]) else 0
        abs_non_just = int(vs_row.iloc[0]["AbsencesNonJustifiees"]) if "AbsencesNonJustifiees" in vs_row.columns and pd.notna(vs_row.iloc[0]["AbsencesNonJustifiees"]) else 0
        retards = int(vs_row.iloc[0]["Retards"]) if "Retards" in vs_row.columns and pd.notna(vs_row.iloc[0]["Retards"]) else 0
        heures_p = int(vs_row.iloc[0]["HeuresPerdues"]) if "HeuresPerdues" in vs_row.columns and pd.notna(vs_row.iloc[0]["HeuresPerdues"]) else 0
        obs = str(vs_row.iloc[0]["Observations"]) if "Observations" in vs_row.columns and pd.notna(vs_row.iloc[0]["Observations"]) else "RAS"
        decision = str(vs_row.iloc[0]["DecisionConseil"]) if "DecisionConseil" in vs_row.columns and pd.notna(vs_row.iloc[0]["DecisionConseil"]) else "Encouragements"

    return {
        "eleve": eleve, "classe": classe, "cycle": cycle_classe, "periode": periode,
        "lignes": lignes_bulletin, "total_points": round(total_points_global, 2),
        "total_coefficients": total_coefficients_global if not is_elem else "-",
        "total_bareme": 10.0 if is_elem else 20.0, "moyenne_generale": moyenne_generale,
        "rang": rang, "effectif": len(tous_eleves), "abs_just": abs_just,
        "abs_non_just": abs_non_just, "retards": retards, "heures_perdues": heures_p,
        "observations": obs, "decision": decision
    }

JOURS_LIST = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]
HEURES_LIST = ["08h-09h", "09h-10h", "10h-11h", "11h00-11h30", "11h30-12h", "12h-13h", "13h-14h", "14h-15h", "15h-16h", "16h-17h", "17h-18h", "18h-19h"]

def get_or_create_edt(classe):
    if "edt_grid_db" not in st.session_state: st.session_state.edt_grid_db = {}
    if classe not in st.session_state.edt_grid_db:
        df_def = pd.DataFrame("", index=JOURS_LIST, columns=HEURES_LIST)
        if "11h00-11h30" in df_def.columns: df_def["11h00-11h30"] = "Récréation"
        st.session_state.edt_grid_db[classe] = df_def
    return st.session_state.edt_grid_db[classe]

# --- MODULE PARENT INTERFACE ---
def afficher_espace_parents():
    st.markdown('<div style="color: #0F172A; font-size: 2.2rem; font-weight: 900;">Espace Parents & Suivi Pédagogique Transparent</div>', unsafe_allow_html=True)

    if "parent_logged" not in st.session_state: st.session_state.parent_logged = False
    if "parent_eleve_sel" not in st.session_state: st.session_state.parent_eleve_sel = ""
    if "parent_classe_sel" not in st.session_state: st.session_state.parent_classe_sel = ""

    if not st.session_state.parent_logged:
        st.info("Veuillez vous authentifier par Téléphone/Email ou Nom de l'élève pour accéder au suivi personnalisé.")
        with st.form("form_login_parent"):
            col_p1, col_p2 = st.columns(2)
            with col_p1: par_ident = st.text_input("Numéro de téléphone ou Email du Parent", value="771234567")
            with col_p2: nom_eleve_par = st.text_input("Nom ou Prénom de l'élève", value="issa")
            btn_par_login = st.form_submit_button("Accéder au Portail Parent")

            if btn_par_login:
                match_p, el_trouve, cl_trouvee = False, "", ""
                ident_clean, nom_clean = par_ident.strip().lower(), nom_eleve_par.strip().lower()

                if "parents_white_list" in st.session_state and not st.session_state.parents_white_list.empty:
                    for _, r in st.session_state.parents_white_list.iterrows():
                        tel = str(r.get("Téléphone", r.get("téléphone", r.get("telephone", "")))).strip().lower()
                        p_e = str(r.get("Prénom Élève", r.get("prénom élève", r.get("prenom eleve", "")))).strip().lower()
                        n_e = str(r.get("Nom Élève", r.get("nom élève", r.get("nom eleve", "")))).strip().lower()
                        if (ident_clean == tel or ident_clean == ADMIN_EMAIL.lower()) and (nom_clean in p_e or nom_clean in n_e or not nom_clean):
                            match_p = True
                            el_trouve = f"{r.get('Prénom Élève', '')} {r.get('Nom Élève', '')}".strip()
                            cl_trouvee = str(r.get("Classe", "6ème A"))
                            break

                if not match_p and ("eleves_db" in st.session_state and not st.session_state.eleves_db.empty):
                    for _, r in st.session_state.eleves_db.iterrows():
                        nc = str(r.get("Nom Complet", "")).strip().lower()
                        if nom_clean and (nom_clean in nc):
                            match_p = True
                            el_trouve = str(r.get("Nom Complet", ""))
                            cl_trouvee = str(r.get("Classe", "6ème A"))
                            break

                if match_p or ident_clean == ADMIN_EMAIL.lower():
                    st.session_state.parent_logged = True
                    st.session_state.parent_eleve_sel = el_trouve if el_trouve else "Issa"
                    st.session_state.parent_classe_sel = cl_trouvee if cl_trouvee else "6ème A"
                    st.success("Connexion réussie !")
                    st.rerun()
                else:
                    st.error("Combinaison introuvable dans le système. Veuillez vérifier vos informations.")
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
            """, unsafe_allow_html=True
        )

        if st.button("Se déconnecter du portail parent"):
            st.session_state.parent_logged = False
            st.session_state.parent_eleve_sel = ""
            st.session_state.parent_classe_sel = ""
            st.rerun()

        st.markdown("---")
        tp_taf, tp_bulletin, tp_edt, tp_msg = st.tabs(["📌 Travail à Faire & Devoirs", "📊 Bulletin & Notes", "📅 Emploi du Temps (Récréation 11h00-11h30)", "💬 Communications & Messages"])

        with tp_taf:
            st.markdown("### 📌 Travaux à Faire & Exercices Assignés")
            df_taf_p = pd.DataFrame()
            if "travail_a_faire_db" in st.session_state and not st.session_state.travail_a_faire_db.empty and "Classe" in st.session_state.travail_a_faire_db.columns:
                df_taf_p = st.session_state.travail_a_faire_db[(st.session_state.travail_a_faire_db["Classe"] == classe_p) | (st.session_state.travail_a_faire_db["Classe"] == "Toutes les classes")]

            if not df_taf_p.empty:
                for _, row in df_taf_p.iterrows():
                    st.markdown(
                        f"""
                        <div style="background-color: #F8FAFC; padding: 15px; border-radius: 10px; margin-bottom: 15px;">
                            <h4 style="color: #0EA5E9; margin: 0 0 10px 0;">{row.get('Titre', 'Devoir')} ({row.get('Matière', 'Général')})</h4>
                            <p style="margin: 0 0 8px 0; color: #334155;"><b>Professeur :</b> {row.get('Professeur', 'N/A')} | <b>À rendre pour le :</b> <span style="color: #DC2626; font-weight: 800;">{row.get('DateRendu', 'N/A')}</span></p>
                            <p style="margin: 0; color: #0F172A; font-size: 1.05rem;">{row.get('Consignes', '')}</p>
                        </div>
                        """, unsafe_allow_html=True
                    )
                    col_m1, col_m2, col_m3 = st.columns(3)
                    with col_m1:
                        if row.get("LienUrl"): st.markdown(f"🔗 [Accéder au Lien Web]({row.get('LienUrl')})")
                    with col_m2:
                        if row.get("LienVideo"): st.markdown(f"🎥 [Visionner la Vidéo]({row.get('LienVideo')})")
                    with col_m3:
                        if row.get("FichierB64") and row.get("FichierNom"):
                            try:
                                f_bytes = base64.b64decode(row.get("FichierB64"))
                                st.download_button(f"📥 Télécharger {row.get('FichierNom')}", data=f_bytes, file_name=row.get("FichierNom"), key=f"dl_taf_{row.get('ID', row.get('Titre'))}")
                            except Exception: pass
                    st.markdown("<hr style='margin: 15px 0;'>", unsafe_allow_html=True)
            else:
                st.info("Aucun travail à faire pour le moment.")

        with tp_bulletin:
            st.markdown("### 📊 Bulletin de Notes Officiel")
            periodes_p = obtenir_periodes_pour_classe(classe_p)
            if periodes_p:
                per_sel_p = st.selectbox("Sélectionner la période", periodes_p, key="p_per_sel_bul")
                bul_data_p = calculer_bulletin_eleve(classe_p, eleve_p, per_sel_p)
                col_b1, col_b2, col_b3 = st.columns(3)
                with col_b1: st.metric("Moyenne Générale", f"{bul_data_p['moyenne_generale']} / {bul_data_p['total_bareme']}")
                with col_b2: st.metric("Rang dans la Classe", bul_data_p['rang'])
                with col_b3: st.metric("Effectif Total", f"{bul_data_p['effectif']} élèves")
                st.dataframe(pd.DataFrame(bul_data_p['lignes']), use_container_width=True)

        with tp_edt:
            st.markdown(f"### 📅 Emploi du Temps Officiel - {classe_p}")
            edt_parent_df = get_or_create_edt(classe_p)
            st.dataframe(edt_parent_df, use_container_width=True)

        with tp_msg:
    st.markdown("### 💬 Communication Directe avec l'Administration")
    with st.form("form_msg_parent"):
        objet_m = st.text_input("Objet de la demande")
        msg_m = st.text_area("Message")
        urgent_m = st.checkbox("Signaler comme Urgent ⚠️")
        
        if st.form_submit_button("Envoyer à l'Administration"):
            if objet_m and msg_m:
                msg_id = f"MSG-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                emetteur_val = f"Parent de {eleve_p}"
                date_val = datetime.now().strftime("%Y-%m-%d %H:%M")

                nouveau_msg = {
                    "ID": msg_id,
                    "Emetteur": emetteur_val,
                    "RoleEmetteur": "Parent",
                    "DateEnvoi": date_val,
                    "Classe": classe_p,
                    "Objet": objet_m,
                    "Message": msg_m,
                    "Urgent": urgent_m
                }

                # 1. Mise à jour immédiate dans la session locale (IHM fluide)
                st.session_state.messages_parents_db = pd.concat(
                    [st.session_state.messages_parents_db, pd.DataFrame([nouveau_msg])], 
                    ignore_index=True
                )

                # 2. Tentative de sauvegarde dans Supabase avec contournement des erreurs DNS
                saved_to_cloud = False
                try:
                    supabase.table("messages_parents").insert({
                        "id": msg_id,
                        "emetteur": emetteur_val,
                        "role_emetteur": "Parent",
                        "date_envoi": date_val,
                        "classe": classe_p,
                        "objet": objet_m,
                        "message": msg_m,
                        "urgent": urgent_m
                    }).execute()
                    saved_to_cloud = True
                except Exception as e:
                    # Capturer explicitement les erreurs de connexion DNS / réseau
                    err_msg = str(e)
                    if "[Errno -2]" in err_msg or "Name or service not known" in err_msg:
                        st.warning("⚠️ Problème de connexion au serveur distant (DNS). Votre message est enregistré en mémoire locale pour cette session.")
                    else:
                        st.warning(f"⚠️ Erreur de synchronisation cloud : {e}")

                if saved_to_cloud:
                    st.success("✅ Message transmis et synchronisé sur la base de données !")
                else:
                    st.info("ℹ️ Le message est sauvegardé localement.")
            else:
                st.error("Veuillez remplir l'objet et le message.")

# --- POINT D'ENTRÉE DU SCRIPT STREAMLIT ---
if __name__ == "__main__":
    afficher_espace_parents()
