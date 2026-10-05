# -*- coding: utf-8 -*-
"""
Universi dei titoli per lo scanner MM200 — Italia, Germania, Francia.

  IT · Piazza Affari      (.MI)  — FTSE MIB, Mid Cap, STAR      → TITOLI
  DE · Germania (Xetra)   (.DE)  — DAX 40, MDAX/SDAX            → TITOLI_DE
  FR · Francia (Parigi)   (.PA)  — CAC 40, CAC Mid 60           → TITOLI_FR

Il mercato "corrente" si sceglie con imposta_mercato("IT"|"DE"|"FR"): da quel
momento BENCHMARK, per_indice(), solo_ticker() e mappa_nomi() rispondono per
quel mercato, quindi tutto il resto del progetto (selezione, punteggi,
dashboard) funziona su un mercato qualsiasi senza altre modifiche.

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

# ------------------------- GERMANIA (Xetra) -------------------------
TITOLI_DE = [
    ("ADS.DE",      "Adidas",  "DAX"),
    ("AIR.DE",      "Airbus",  "DAX"),
    ("ALV.DE",      "Allianz", "DAX"),
    ("BAS.DE",      "BASF",    "DAX"),
    ("BAYN.DE",     "Bayer",   "DAX"),
    ("BEI.DE",      "Beiersdorf", "DAX"),
    ("BMW.DE",      "BMW",     "DAX"),
    ("BNR.DE",      "Brenntag", "DAX"),
    ("CBK.DE",      "Commerzbank", "DAX"),
    ("CON.DE",      "Continental", "DAX"),
    ("DB1.DE",      "Deutsche Börse", "DAX"),
    ("DBK.DE",      "Deutsche Bank", "DAX"),
    ("DHL.DE",      "Deutsche Post", "DAX"),
    ("DTE.DE",      "Deutsche Telekom", "DAX"),
    ("DTG.DE",      "Daimler Truck", "DAX"),
    ("ENR.DE",      "Siemens Energy", "DAX"),
    ("EOAN.DE",     "E.ON",    "DAX"),
    ("FME.DE",      "Fresenius Medical Care", "DAX"),
    ("FRE.DE",      "Fresenius", "DAX"),
    ("HEI.DE",      "Heidelberg Materials", "DAX"),
    ("HEN3.DE",     "Henkel",  "DAX"),
    ("HNR1.DE",     "Hannover Rück", "DAX"),
    ("IFX.DE",      "Infineon", "DAX"),
    ("MBG.DE",      "Mercedes-Benz", "DAX"),
    ("MRK.DE",      "Merck KGaA", "DAX"),
    ("MTX.DE",      "MTU Aero Engines", "DAX"),
    ("MUV2.DE",     "Munich Re", "DAX"),
    ("P911.DE",     "Porsche AG", "DAX"),
    ("PAH3.DE",     "Porsche Automobil Holding", "DAX"),
    ("QIA.DE",      "Qiagen",  "DAX"),
    ("RHM.DE",      "Rheinmetall", "DAX"),
    ("RWE.DE",      "RWE",     "DAX"),
    ("SAP.DE",      "SAP",     "DAX"),
    ("SHL.DE",      "Siemens Healthineers", "DAX"),
    ("SIE.DE",      "Siemens", "DAX"),
    ("SRT3.DE",     "Sartorius", "DAX"),
    ("SY1.DE",      "Symrise", "DAX"),
    ("VNA.DE",      "Vonovia", "DAX"),
    ("VOW3.DE",     "Volkswagen", "DAX"),
    ("ZAL.DE",      "Zalando", "DAX"),
    ("AFX.DE",      "Carl Zeiss", "MDAX"),
    ("AIXA.DE",     "Aixtron", "MDAX"),
    ("AT1.DE",      "Aroundtown", "MDAX"),
    ("BC8.DE",      "Bechtle", "MDAX"),
    ("BOSS.DE",     "Hugo Boss", "MDAX"),
    ("DHER.DE",     "Delivery Hero", "MDAX"),
    ("ELG.DE",      "Elmos",   "MDAX"),
    ("EVD.DE",      "CTS Eventim", "MDAX"),
    ("EVK.DE",      "Evonik",  "MDAX"),
    ("FNTN.DE",     "freenet", "MDAX"),
    ("FRA.DE",      "Fraport", "MDAX"),
    ("G1A.DE",      "GEA Group", "MDAX"),
    ("G24.DE",      "Scout24", "MDAX"),
    ("GBF.DE",      "Bilfinger", "MDAX"),
    ("GXI.DE",      "Gerresheimer", "MDAX"),
    ("HFG.DE",      "HelloFresh", "MDAX"),
    ("HOT.DE",      "Hochtief", "MDAX"),
    ("INH.DE",      "Indus Holding", "MDAX"),
    ("JEN.DE",      "Jenoptik", "MDAX"),
    ("JUN3.DE",     "Jungheinrich", "MDAX"),
    ("KBX.DE",      "Knorr-Bremse", "MDAX"),
    ("KGX.DE",      "KION Group", "MDAX"),
    ("KRN.DE",      "Krones",  "MDAX"),
    ("LEG.DE",      "LEG Immobilien", "MDAX"),
    ("LHA.DE",      "Lufthansa", "MDAX"),
    ("MBB.DE",      "MBB",     "MDAX"),
    ("NDA.DE",      "Aurubis", "MDAX"),
    ("NDX1.DE",     "Nordex",  "MDAX"),
    ("NEM.DE",      "Nemetschek", "MDAX"),
    ("PUM.DE",      "Puma",    "MDAX"),
    ("RAA.DE",      "Rational", "MDAX"),
    ("S92.DE",      "SMA Solar", "MDAX"),
    ("SDF.DE",      "K+S",     "MDAX"),
    ("SFQ.DE",      "SAF-Holland", "MDAX"),
    ("SZG.DE",      "Salzgitter", "MDAX"),
    ("TEG.DE",      "TAG Immobilien", "MDAX"),
    ("TKA.DE",      "thyssenkrupp", "MDAX"),
    ("TLX.DE",      "Talanx",  "MDAX"),
    ("VH2.DE",      "Friedrich Vorwerk", "MDAX"),
    ("WAF.DE",      "Siltronic", "MDAX"),
    ("WCH.DE",      "Wacker Chemie", "MDAX"),
]

# ------------------------- FRANCIA (Parigi) -------------------------
TITOLI_FR = [
    ("AC.PA",       "Accor",   "CAC"),
    ("ACA.PA",      "Crédit Agricole", "CAC"),
    ("AI.PA",       "Air Liquide", "CAC"),
    ("AIR.PA",      "Airbus",  "CAC"),
    ("ALO.PA",      "Alstom",  "CAC"),
    ("BN.PA",       "Danone",  "CAC"),
    ("BNP.PA",      "BNP Paribas", "CAC"),
    ("BVI.PA",      "Bureau Veritas", "CAC"),
    ("CA.PA",       "Carrefour", "CAC"),
    ("CAP.PA",      "Capgemini", "CAC"),
    ("CS.PA",       "AXA",     "CAC"),
    ("DG.PA",       "Vinci",   "CAC"),
    ("DSY.PA",      "Dassault Systèmes", "CAC"),
    ("EDEN.PA",     "Edenred", "CAC"),
    ("EL.PA",       "EssilorLuxottica", "CAC"),
    ("EN.PA",       "Bouygues", "CAC"),
    ("ENGI.PA",     "Engie",   "CAC"),
    ("ERF.PA",      "Eurofins Scientific", "CAC"),
    ("GLE.PA",      "Société Générale", "CAC"),
    ("HO.PA",       "Thales",  "CAC"),
    ("KER.PA",      "Kering",  "CAC"),
    ("LR.PA",       "Legrand", "CAC"),
    ("MC.PA",       "LVMH",    "CAC"),
    ("ML.PA",       "Michelin", "CAC"),
    ("OR.PA",       "L'Oréal", "CAC"),
    ("ORA.PA",      "Orange",  "CAC"),
    ("PUB.PA",      "Publicis", "CAC"),
    ("RI.PA",       "Pernod Ricard", "CAC"),
    ("RNO.PA",      "Renault", "CAC"),
    ("SAF.PA",      "Safran",  "CAC"),
    ("SAN.PA",      "Sanofi",  "CAC"),
    ("SGO.PA",      "Saint-Gobain", "CAC"),
    ("STLAP.PA",    "Stellantis", "CAC"),
    ("STMPA.PA",    "STMicroelectronics", "CAC"),
    ("SU.PA",       "Schneider Electric", "CAC"),
    ("TEP.PA",      "Teleperformance", "CAC"),
    ("TTE.PA",      "TotalEnergies", "CAC"),
    ("URW.PA",      "Unibail-Rodamco-Westfield", "CAC"),
    ("VIE.PA",      "Veolia",  "CAC"),
    ("WLN.PA",      "Worldline", "CAC"),
    ("AF.PA",       "Air France-KLM", "MID"),
    ("AKE.PA",      "Arkema",  "MID"),
    ("ATE.PA",      "Alten",   "MID"),
    ("BB.PA",       "BIC",     "MID"),
    ("BIM.PA",      "bioMérieux", "MID"),
    ("BOL.PA",      "Bolloré", "MID"),
    ("CARM.PA",     "Carmila", "MID"),
    ("COFA.PA",     "Coface",  "MID"),
    ("DBG.PA",      "Derichebourg", "MID"),
    ("DEC.PA",      "JCDecaux", "MID"),
    ("DIM.PA",      "Sartorius Stedim Biotech", "MID"),
    ("ELIS.PA",     "Elis",    "MID"),
    ("ETL.PA",      "Eutelsat", "MID"),
    ("FGR.PA",      "Eiffage", "MID"),
    ("FR.PA",       "Valeo",   "MID"),
    ("FRVIA.PA",    "Forvia",  "MID"),
    ("GET.PA",      "Getlink", "MID"),
    ("GTT.PA",      "GTT",     "MID"),
    ("IPN.PA",      "Ipsen",   "MID"),
    ("ITP.PA",      "Interparfums", "MID"),
    ("LSS.PA",      "Lectra",  "MID"),
    ("MF.PA",       "Wendel",  "MID"),
    ("MMB.PA",      "Lagardère", "MID"),
    ("MRN.PA",      "Mersen",  "MID"),
    ("NEX.PA",      "Nexans",  "MID"),
    ("NK.PA",       "Imerys",  "MID"),
    ("RF.PA",       "Eurazeo", "MID"),
    ("RUI.PA",      "Rubis",   "MID"),
    ("RXL.PA",      "Rexel",   "MID"),
    ("SCR.PA",      "SCOR",    "MID"),
    ("SK.PA",       "SEB",     "MID"),
    ("SOP.PA",      "Sopra Steria", "MID"),
    ("SPIE.PA",     "SPIE",    "MID"),
    ("SW.PA",       "Sodexo",  "MID"),
    ("TE.PA",       "Technip Energies", "MID"),
    ("TRI.PA",      "Trigano", "MID"),
    ("UBI.PA",      "Ubisoft", "MID"),
    ("VCT.PA",      "Vicat",   "MID"),
    ("VIRP.PA",     "Virbac",  "MID"),
    ("VK.PA",       "Vallourec", "MID"),
]

# ---------------------------------------------------------------------------
#  Registro dei mercati
# ---------------------------------------------------------------------------
MERCATI = {
    "IT": {
        "nome": "Piazza Affari",
        "paese": "Italia",
        "suffisso": ".MI",
        "benchmark": "FTSEMIB.MI",
        "benchmark_nome": "FTSE MIB",
        "titoli": TITOLI,
    },
    "DE": {
        "nome": "Xetra",
        "paese": "Germania",
        "suffisso": ".DE",
        "benchmark": "^GDAXI",
        "benchmark_nome": "DAX",
        "titoli": TITOLI_DE,
    },
    "FR": {
        "nome": "Parigi",
        "paese": "Francia",
        "suffisso": ".PA",
        "benchmark": "^FCHI",
        "benchmark_nome": "CAC 40",
        "titoli": TITOLI_FR,
    },
}

mercato = "IT"                       # mercato corrente (IT / DE / FR)

# Indice di riferimento per i confronti (benchmark) — dipende dal mercato
BENCHMARK = MERCATI["IT"]["benchmark"]
BENCHMARK_NOME = MERCATI["IT"]["benchmark_nome"]


_OSSERVATORI = []


def osserva(funzione):
    """Registra una funzione da richiamare a ogni cambio di mercato.

    Serve ai moduli che tengono in memoria percorsi di file (cache, output):
    si iscrivono qui e i loro percorsi seguono il mercato automaticamente."""
    _OSSERVATORI.append(funzione)
    try:                     # allineamento immediato al mercato già attivo
        funzione(mercato)
    except Exception:
        pass
    return funzione


def imposta_mercato(codice="IT"):
    """Cambia il mercato corrente. Ritorna il dizionario del mercato."""
    global mercato, BENCHMARK, BENCHMARK_NOME, TITOLI
    cod = (codice or "IT").upper()
    if cod not in MERCATI:
        raise ValueError(f"mercato sconosciuto: {cod} (scegli fra {', '.join(MERCATI)})")
    mercato = cod
    BENCHMARK = MERCATI[cod]["benchmark"]
    BENCHMARK_NOME = MERCATI[cod]["benchmark_nome"]
    TITOLI = MERCATI[cod]["titoli"]
    for f in _OSSERVATORI:
        try:
            f(cod)
        except Exception:
            pass
    return MERCATI[cod]


def info(codice=None):
    """Dati del mercato (corrente se non specificato)."""
    return MERCATI[(codice or mercato).upper()]


def percorso(nome_file, codice=None):
    """Percorso di un file di lavoro, distinto per mercato.

    L'Italia tiene i nomi storici (scanner_live.pkl) per non invalidare le
    cache già costruite; gli altri mercati hanno il suffisso del mercato
    (scanner_live_DE.pkl, scanner_live_FR.pkl)."""
    cod = (codice or mercato).upper()
    if cod == "IT":
        return nome_file
    if "." in nome_file:
        base, ext = nome_file.rsplit(".", 1)
        return f"{base}_{cod}.{ext}"
    return f"{nome_file}_{cod}"


def elenco_mercati():
    """Elenco dei codici mercato disponibili."""
    return list(MERCATI)


def per_indice(indice="TUTTI"):
    """Ritorna la lista (ticker, nome, indice) del mercato corrente."""
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
    for cod in elenco_mercati():
        m = imposta_mercato(cod)
        print(f"{cod} · {m['paese']} ({m['nome']}) — {len(m['titoli'])} titoli · benchmark {m['benchmark_nome']} ({m['benchmark']})")
        for idx in sorted({t[2] for t in m["titoli"]}):
            print(f"    {idx}: {len(per_indice(idx))}")
