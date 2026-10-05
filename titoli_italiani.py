# -*- coding: utf-8 -*-
"""
Universo di titoli di Borsa Italiana (Piazza Affari) per lo scanner MM200.

Copre le tre principali famiglie di indici FTSE Italia:
  - FTSE MIB          (40 blue chip)
  - FTSE Italia Mid Cap (medie capitalizzazioni)
  - FTSE Italia STAR   (small cap con requisiti di governance)

I ticker seguono la convenzione Yahoo Finance: <simbolo>.MI
Es. ENI -> ENI.MI, Intesa Sanpaolo -> ISP.MI

Nota: la composizione degli indici cambia ogni trimestre. Le liste sono
volutamente sovradimensionate: il modulo `scanner.py` scarta in automatico
i ticker che non hanno dati (delisting, fusioni, cambi di simbolo) e li
segnala nel report.
"""

# (ticker, nome, indice)
TITOLI = [
    # ------------------------- FTSE MIB -------------------------
    ("A2A.MI",    "A2A",                        "MIB"),
    ("AMP.MI",    "Amplifon",                   "MIB"),
    ("AZM.MI",    "Azimut Holding",             "MIB"),
    ("BC.MI",     "Brunello Cucinelli",         "MIB"),
    ("BGN.MI",    "Banca Generali",             "MIB"),
    ("BMED.MI",   "Banca Mediolanum",           "MIB"),
    ("BMPS.MI",   "Banca Monte dei Paschi",     "MIB"),
    ("BPE.MI",    "BPER Banca",                 "MIB"),
    ("BRE.MI",    "Brembo",                     "MIB"),
    ("BZU.MI",    "Buzzi",                      "MIB"),
    ("CPR.MI",    "Campari",                    "MIB"),
    ("DIA.MI",    "DiaSorin",                   "MIB"),
    ("ENEL.MI",   "Enel",                       "MIB"),
    ("ENI.MI",    "Eni",                        "MIB"),
    ("ERG.MI",    "ERG",                        "MIB"),
    ("FBK.MI",    "FinecoBank",                 "MIB"),
    ("FCT.MI",    "Fincantieri",                "MIB"),
    ("G.MI",      "Assicurazioni Generali",     "MIB"),
    ("HER.MI",    "Hera",                       "MIB"),
    ("IG.MI",     "Italgas",                    "MIB"),
    ("INW.MI",    "INWIT",                      "MIB"),
    ("IP.MI",     "Interpump Group",            "MIB"),
    ("ISP.MI",    "Intesa Sanpaolo",            "MIB"),
    ("IVG.MI",    "Iveco Group",                "MIB"),
    ("LDO.MI",    "Leonardo",                   "MIB"),
    ("MB.MI",     "Mediobanca",                 "MIB"),
    ("MONC.MI",   "Moncler",                    "MIB"),
    ("NEXI.MI",   "Nexi",                       "MIB"),
    ("PIRC.MI",   "Pirelli",                    "MIB"),
    ("PRY.MI",    "Prysmian",                   "MIB"),
    ("PST.MI",    "Poste Italiane",             "MIB"),
    ("RACE.MI",   "Ferrari",                    "MIB"),
    ("REC.MI",    "Recordati",                  "MIB"),
    ("SPM.MI",    "Saipem",                     "MIB"),
    ("SRG.MI",    "Snam",                       "MIB"),
    ("STLAM.MI",  "Stellantis",                 "MIB"),
    ("STMMI.MI",  "STMicroelectronics",         "MIB"),
    ("TEN.MI",    "Tenaris",                    "MIB"),
    ("TIT.MI",    "Telecom Italia",             "MIB"),
    ("TRN.MI",    "Terna",                      "MIB"),
    ("UCG.MI",    "UniCredit",                  "MIB"),
    ("UNI.MI",    "Unipol",                     "MIB"),
    ("TGYM.MI",   "Technogym",                  "MIB"),
    ("WBD.MI",    "Webuild",                    "MIB"),
    ("SL.MI",     "Sanlorenzo",                 "MIB"),
    ("PIA.MI",    "Piaggio",                    "MIB"),

    # --------------------- FTSE Italia Mid Cap ------------------
    ("ACE.MI",    "Acea",                       "MID"),
    ("ANIM.MI",   "Anima Holding",              "MID"),
    ("ASC.MI",    "Ascopiave",                  "MID"),
    ("BFF.MI",    "BFF Bank",                   "MID"),
    ("BDB.MI",    "Banco di Desio e Brianza",   "MID"),
    ("CALT.MI",   "Caltagirone",                "MID"),
    ("CRL.MI",    "Carel Industries",           "MID"),
    ("CMB.MI",    "Cembre",                     "MID"),
    ("CEM.MI",    "Cementir Holding",           "MID"),
    ("CIR.MI",    "CIR",                        "MID"),
    ("CE.MI",     "Credito Emiliano",           "MID"),
    ("DAN.MI",    "Danieli & C.",               "MID"),
    ("DIS.MI",    "d'Amico International",      "MID"),
    ("DLG.MI",    "De'Longhi",                  "MID"),
    ("ELN.MI",    "El.En.",                     "MID"),
    ("ENV.MI",    "ENAV",                       "MID"),
    ("FM.MI",     "Fiera Milano",               "MID"),
    ("GHC.MI",    "Garofalo Health Care",       "MID"),
    ("GVS.MI",    "GVS",                        "MID"),
    ("IGD.MI",    "IGD SIIQ",                   "MID"),
    ("ICOS.MI",   "Intercos",                   "MID"),
    ("IRE.MI",    "Iren",                       "MID"),
    ("ITM.MI",    "Italmobiliare",              "MID"),
    ("JUVE.MI",   "Juventus FC",                "MID"),
    ("LUVE.MI",   "LU-VE",                      "MID"),
    ("MAIRE.MI",  "Maire",                      "MID"),
    ("MARR.MI",   "MARR",                       "MID"),
    ("MFEA.MI",   "MFE-MediaForEurope A",       "MID"),
    ("MFEB.MI",   "MFE-MediaForEurope B",       "MID"),
    ("MOL.MI",    "Moltiply Group",             "MID"),
    ("MN.MI",     "Arnoldo Mondadori Editore",  "MID"),
    ("OVS.MI",    "OVS",                        "MID"),
    ("PHN.MI",    "Pharmanutra",                "MID"),
    ("RWY.MI",    "Rai Way",                    "MID"),
    ("RCS.MI",    "RCS MediaGroup",             "MID"),
    ("REY.MI",    "Reply",                      "MID"),
    ("REVO.MI",   "Revo Insurance",             "MID"),
    ("SFER.MI",   "Salvatore Ferragamo",        "MID"),
    ("SES.MI",    "Sesa",                       "MID"),
    ("SOL.MI",    "SOL",                        "MID"),
    ("TIP.MI",    "Tamburi Investment Partners","MID"),
    ("TPRO.MI",   "Technoprobe",                "MID"),
    ("WIIT.MI",   "WIIT",                       "MID"),
    ("ZV.MI",     "Zignago Vetro",              "MID"),
    ("IF.MI",     "Banca IFIS",                 "MID"),
    ("BST.MI",    "Banca Sistema",              "MID"),
    ("SFL.MI",    "Safilo Group",               "MID"),
    ("TISG.MI",   "The Italian Sea Group",      "MID"),
    ("TNX.MI",    "Tinexta",                    "MID"),
    ("ORS.MI",    "Orsero",                     "MID"),
    ("SAB.MI",    "Sabaf",                      "MID"),
    ("EM.MI",     "Emak",                       "MID"),
    ("PRT.MI",    "Esprinet",                   "MID"),
    ("DAL.MI",    "Datalogic",                  "MID"),
    ("BSS.MI",    "Biesse",                     "MID"),
    ("AVIO.MI",   "Avio",                       "MID"),
    ("ECNL.MI",   "Aquafil",                    "MID"),
    ("CELL.MI",   "Cellularline",               "MID"),
    ("FILA.MI",   "FILA",                       "MID"),
    ("DIB.MI",    "Digital Bros",               "MID"),
    ("TXT.MI",    "TXT e-solutions",            "MID"),
    ("IOT.MI",    "Seco",                       "MID"),
    ("CY4.MI",    "CY4Gate",                    "MID"),
    ("GE.MI",     "Gefran",                     "MID"),
    ("ELC.MI",    "Elica",                      "MID"),
    ("TES.MI",    "Tesmec",                     "MID"),
    ("ETH.MI",    "Eurotech",                   "MID"),
    ("LNDR.MI",   "Landi Renzo",                "MID"),
    ("SGF.MI",    "Sogefi",                     "MID"),
    ("SYS.MI",    "SYS-DAT",                    "MID"),
    ("NDT.MI",    "Neodecortech",               "MID"),
    ("FF.MI",     "Fine Foods & Pharma",        "MID"),
    ("UD.MI",     "Unidata",                    "MID"),
    ("EQUI.MI",   "Equita Group",               "MID"),
    ("GF.MI",     "Generalfinance",             "MID"),
    ("DOV.MI",    "doValue",                    "MID"),
    ("AGP.MI",    "Altea Green Power",          "MID"),
    ("BEC.MI",    "B&C Speakers",               "MID"),
    ("AEF.MI",    "Aeffe",                      "MID"),
    ("ABT.MI",    "Abitare In",                 "MID"),
    ("ADB.MI",    "Aeroporto di Bologna",       "MID"),
    ("CAI.MI",    "Cairo Communication",        "MID"),
    ("COM.MI",    "Comer Industries",           "MID"),
    ("PHIL.MI",   "Philogen",                   "MID"),
]

# Indice di riferimento per i confronti (benchmark)
BENCHMARK = "FTSEMIB.MI"
BENCHMARK_NOME = "FTSE MIB"


def per_indice(indice="TUTTI"):
    """Ritorna la lista (ticker, nome, indice) filtrata per indice."""
    if indice.upper() in ("TUTTI", "ALL", "*"):
        return list(TITOLI)
    return [t for t in TITOLI if t[2].upper() == indice.upper()]


def solo_ticker(indice="TUTTI"):
    """Ritorna la lista dei soli simboli Yahoo."""
    return [t[0] for t in per_indice(indice)]


def mappa_nomi():
    """Dizionario ticker -> nome leggibile."""
    return {t[0]: t[1] for t in TITOLI}


if __name__ == "__main__":
    print(f"Universo: {len(TITOLI)} ticker")
    for idx in ("MIB", "MID"):
        print(f"  {idx}: {len(per_indice(idx))}")
