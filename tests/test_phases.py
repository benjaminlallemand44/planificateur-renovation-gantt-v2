import pytest

from renovation_gantt.phases import (
    GLOSSAIRE_COMPLET,
    GLOSSAIRE_COURT,
    LIBELLES_GLOSSAIRE,
    EtatProjet,
    Groupe,
    financement_disponible,
    phases_pour_etat,
)

ETAPES_MOP = ["DIAG", "ESQ", "APS", "APD", "AUTORISATIONS", "PRO", "DCE", "ACT", "VISA", "DET", "AOR"]


def ids(etat):
    return [p.id for p in phases_pour_etat(etat)]


@pytest.mark.parametrize("etat", list(EtatProjet))
def test_toutes_les_etapes_mop_sont_presentes_dans_l_ordre(etat):
    assert [i for i in ids(etat) if i in ETAPES_MOP] == ETAPES_MOP


@pytest.mark.parametrize("etat", list(EtatProjet))
def test_identifiants_uniques(etat):
    assert len(ids(etat)) == len(set(ids(etat)))


def test_sans_audit():
    groupes = {p.groupe for p in phases_pour_etat(EtatProjet.SANS_AUDIT)}
    assert "AUDIT" in ids(EtatProjet.SANS_AUDIT)
    assert Groupe.AMO not in groupes
    assert Groupe.SELECTION_MOE in groupes


def test_audit_recu_inclut_amo_et_analyse_cr():
    liste = ids(EtatProjet.AUDIT_RECU)
    assert "ANALYSE_CR" in liste and "AUDIT" not in liste
    assert liste.index("PROGRAMME") < liste.index("AMO_CHOIX") < liste.index("MOE_CCTP")


def test_amo_programmiste():
    groupes = [p.groupe for p in phases_pour_etat(EtatProjet.AMO_PROGRAMMISTE)]
    assert groupes[0] is Groupe.AMO
    assert Groupe.ETUDES not in groupes


def test_recrutement_moe():
    assert phases_pour_etat(EtatProjet.RECRUTEMENT_MOE)[0].groupe is Groupe.SELECTION_MOE


def test_moe_selectionnee_commence_par_diag_sans_financement():
    assert ids(EtatProjet.MOE_SELECTIONNEE)[0] == "DIAG"
    assert not financement_disponible(EtatProjet.MOE_SELECTIONNEE)
    assert financement_disponible(EtatProjet.SANS_AUDIT)


def test_etat_accepte_la_chaine_de_caracteres():
    assert ids(EtatProjet.SANS_AUDIT.value) == ids(EtatProjet.SANS_AUDIT)


def test_minimums_reglementaires():
    phases = {p.id: p for p in phases_pour_etat(EtatProjet.MOE_SELECTIONNEE)}
    assert phases["APS"].duree_min == 3
    assert phases["APD"].duree_min == 6
    assert phases["PRO"].duree_min == 4
    for p in phases.values():
        assert p.duree >= p.duree_min


def test_esq_masquee():
    esq = next(p for p in phases_pour_etat(EtatProjet.MOE_SELECTIONNEE) if p.id == "ESQ")
    assert not esq.afficher_gantt and not esq.modifiable


def test_glossaire_couvre_toutes_les_etapes_mop():
    for code in ETAPES_MOP:
        assert GLOSSAIRE_COURT[code]
        assert GLOSSAIRE_COMPLET[code]
        assert LIBELLES_GLOSSAIRE[code]
        assert len(GLOSSAIRE_COMPLET[code]) > len(GLOSSAIRE_COURT[code])
