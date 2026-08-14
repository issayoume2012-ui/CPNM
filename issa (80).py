import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

# --- CONFIGURATION & CONNEXION SUPABASE ---
DEFAULT_URL = "https://lqqctacgbknzytikeuya.supabase.co"
DEFAULT_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxxcWN0YWNnYmtuenl0aWtldXlhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODYxMTA2MzAsImV4cCI6MjEwMTY4NjYzMH0.rKfwUOkxwaVAkyXd3wZEJ5AGjWTbJpu0XS0rrllpgn8"

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

# --- CHARGEMENT DES 2 TABLES SEULEMENT ---

def charger_table_supabase(table_name: str, cols_mapping: dict = None) -> pd.DataFrame:
    try:
        res = supabase.table(table_name).select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty and cols_mapping:
            df = df.rename(columns=cols_mapping)
        return df
    except Exception:
        return pd.DataFrame()

# 1. Chargement Liste Blanche Parents
if "parents_white_list" not in st.session_state:
    df_p = charger_table_supabase("parents_white_list", {
        "telephone": "Téléphone",
        "prenom_eleve": "Prénom Élève",
        "nom_eleve": "Nom Élève",
        "classe": "Classe"
    })
    if df_p.empty:
        st.session_state.parents_white_list = pd.DataFrame([
            {"Téléphone": "771234567", "Prénom Élève": "Moussa", "Nom Élève": "Diop", "Classe": "6ème A"}
        ])
    else:
        st.session_state.parents_white_list = df_p

# 2. Chargement Messages Parents
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


# --- INTERFACE STREAMLIT ---

def afficher_espace_parents():
    st.title("💬 Espace Communication Parents")

    if "parent_logged" not in st.session_state: st.session_state.parent_logged = False
    if "parent_eleve_sel" not in st.session_state: st.session_state.parent_eleve_sel = ""
    if "parent_classe_sel" not in st.session_state: st.session_state.parent_classe_sel = ""

    # CONNEXION
    if not st.session_state.parent_logged:
        st.subheader("Connexion Parent")
        with st.form("form_login_parent"):
            par_ident = st.text_input("Numéro de téléphone", value="771234567")
            nom_eleve_par = st.text_input("Prénom ou Nom de l'élève", value="Moussa")
            btn_login = st.form_submit_button("Se connecter")

            if btn_login:
                match_p, el_trouve, cl_trouvee = False, "", ""
                ident_clean = par_ident.strip().lower()
                nom_clean = nom_eleve_par.strip().lower()

                for _, r in st.session_state.parents_white_list.iterrows():
                    tel = str(r.get("Téléphone", "")).strip().lower()
                    p_e = str(r.get("Prénom Élève", "")).strip().lower()
                    n_e = str(r.get("Nom Élève", "")).strip().lower()

                    if ident_clean == tel and (nom_clean in p_e or nom_clean in n_e or not nom_clean):
                        match_p = True
                        el_trouve = f"{r.get('Prénom Élève', '')} {r.get('Nom Élève', '')}".strip()
                        cl_trouvee = str(r.get("Classe", "Non assignée"))
                        break

                if match_p:
                    st.session_state.parent_logged = True
                    st.session_state.parent_eleve_sel = el_trouve
                    st.session_state.parent_classe_sel = cl_trouvee
                    st.success("Connexion réussie !")
                    st.rerun()
                else:
                    st.error("Identifiants introuvables dans la liste autorisée.")
    
    # ESPACE ENVOI DE MESSAGE
    else:
        eleve_p = st.session_state.parent_eleve_sel
        classe_p = st.session_state.parent_classe_sel

        st.info(f"👤 **Élève :** {eleve_p} | 🏫 **Classe :** {classe_p}")

        if st.button("Déconnexion"):
            st.session_state.parent_logged = False
            st.rerun()

        st.markdown("---")
        st.subheader("✉️ Envoyer un message à l'établissement")

        with st.form("form_msg_parent"):
            objet_m = st.text_input("Objet de votre message")
            msg_m = st.text_area("Votre message")
            urgent_m = st.checkbox("Message Urgent ⚠️")
            
            if st.form_submit_button("Envoyer"):
                if objet_m and msg_m:
                    msg_id = f"MSG-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    emetteur_val = f"Parent de {eleve_p}"
                    date_val = datetime.now().strftime("%Y-%m-%d %H:%M")

                    nouveau_msg = {
                        "id": msg_id,
                        "emetteur": emetteur_val,
                        "role_emetteur": "Parent",
                        "date_envoi": date_val,
                        "classe": classe_p,
                        "objet": objet_m,
                        "message": msg_m,
                        "urgent": urgent_m
                    }

                    # Insertion directe dans Supabase
                    try:
                        supabase.table("messages_parents").insert(nouveau_msg).execute()
                        st.success("✅ Message envoyé et enregistré avec succès !")
                    except Exception as e:
                        st.error(f"Erreur d'envoi à la base de données : {e}")
                else:
                    st.warning("Veuillez remplir l'objet et le message.")

if __name__ == "__main__":
    afficher_espace_parents()
