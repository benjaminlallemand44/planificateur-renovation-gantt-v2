"""Textes relatifs aux données personnelles (RGPD) et mentions légales affichés dans l'application."""

EDITEUR = "SASU FNCCR"
DIRECTEUR_PUBLICATION = "Benjamin Lallemand"
CONTACT = "actee@fnccr.asso.fr"
HEBERGEUR = "Snowflake Inc. (service Streamlit Community Cloud), 106 East Babcock Street, Suite 3A, Bozeman, MT 59715, États-Unis"
CONTACT_HEBERGEUR = "privacy@snowflake.com"

BANDEAU = (
    "🔒 **Vos données restent chez vous.** Cet outil ne conserve aucune de vos saisies : elles servent uniquement au "
    "calcul du planning et du budget, le temps de votre visite, et ne sont enregistrées dans aucune base de données. "
    "Nous n'y avons pas accès et ne les réutilisons pas. Merci de ne saisir aucune donnée personnelle (nom, adresse "
    "électronique, téléphone)."
)

CASE_MEMORISER = "Mémoriser mes saisies sur cet appareil"
AIDE_MEMORISER = (
    "Vos paramètres sont alors enregistrés uniquement dans ce navigateur, pour les retrouver à votre prochaine "
    "visite. Ils ne nous sont pas transmis. Décochez la case ou cliquez sur « Nouveau projet » pour les effacer. "
    "À éviter sur un poste partagé."
)

DONNEES_ET_CONFIDENTIALITE = f"""
**Quelles données ?** Les informations que vous saisissez pour votre projet : nom du projet, territoire, durées,
montants et financeurs. L'outil n'a pas besoin de données personnelles : merci de ne pas saisir de noms de personnes,
d'adresses électroniques ou de numéros de téléphone.

**Que deviennent-elles ?**
- Elles sont transmises au serveur de l'application, le temps du calcul, puis effacées à la fermeture de la page.
  Elles ne sont ni stockées dans une base de données, ni analysées, ni partagées, ni utilisées à d'autres fins.
- Si vous cochez « {CASE_MEMORISER} », elles sont enregistrées dans votre navigateur (stockage local), sur votre seul
  appareil. Toute personne utilisant ce même navigateur pourra les voir : évitez cette option sur un poste partagé.
  Rien n'est enregistré sur votre appareil si la case n'est pas cochée.
- Les fichiers exportés (PDF, Excel, agenda, scénario) sont créés à la demande et téléchargés sur votre appareil.
  Aucune copie n'est conservée.

**Hébergement.** L'application est hébergée par Streamlit Community Cloud, service de la société américaine
Snowflake Inc., dans des centres de données de fournisseurs d'infrastructure cloud dont l'hébergeur ne précise pas
le pays. Les échanges sont chiffrés (HTTPS). Vos saisies peuvent donc transiter par des serveurs situés hors de
l'Union européenne, notamment aux États-Unis : Snowflake déclare encadrer ces transferts par le cadre de protection
des données UE–États-Unis (Data Privacy Framework) et les clauses contractuelles types de la Commission européenne.
Comme tout hébergeur, il collecte automatiquement des données techniques de connexion (adresse IP, navigateur,
heures d'accès), selon sa propre politique de confidentialité (contact : {CONTACT_HEBERGEUR}). Les statistiques de
visite mises à notre disposition sont anonymisées.

**Pas de traceurs.** Aucun cookie publicitaire ni outil de mesure d'audience n'est utilisé par l'application.

**Vos droits.** Conformément au Règlement général sur la protection des données (RGPD) et à la loi Informatique et
Libertés, vous pouvez nous contacter pour toute question à l'adresse {CONTACT}. Vous pouvez aussi adresser une
réclamation à la CNIL ([www.cnil.fr](https://www.cnil.fr)).
"""

RAPPEL_BUDGET = (
    "🔒 Les montants saisis ici ne sont pas conservés par l'outil et ne nous sont pas transmis pour un autre usage "
    "que le calcul affiché. Ils peuvent être confidentiels avant leur adoption en conseil : pour partager votre "
    "budget, utilisez les exports et transmettez-les vous-même aux personnes concernées."
)

MENTIONS_LEGALES = f"""
**Éditeur :** {EDITEUR}.

**Directeur de la publication :** {DIRECTEUR_PUBLICATION}.

**Hébergeur :** {HEBERGEUR}.

**Contact :** {CONTACT}.

*Les résultats sont des estimations indicatives et ne remplacent pas l'avis de vos services ou de votre maîtrise
d'œuvre.*
"""
