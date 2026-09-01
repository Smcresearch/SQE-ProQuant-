"""
build_hq_september.py
---------------------
Build the September High Quality universe folder from the confirmed name list.

Unlike build_hq_august.py this does not carry CSVs over from the previous
month's folder: those stopped at 26-08-2026 and three of them had a blank
trailing row, so a clean full-history download for all 153 names is both
shorter and leaves every file current to the same session.

Every ticker below was verified against yfinance on 31-08-2026 — the company
name in the table is the longName Yahoo returned, checked against the screener
name it maps from.

Writes the schema the screener and update_hq_stocks.py expect:
  Symbol,Company,Industry,Index,Date,Open,High,Low,Close,Volume,Dividends,Stock Splits

    python build_hq_september.py --dry-run
    python build_hq_september.py
"""
import os
import sys
import time
from datetime import datetime

import yfinance as yf

DST = os.environ.get('HQ_SEP_DIR', r'D:/Shared folder/portfolio/High_Quality_September')
DATE_FMT = '%d-%m-%Y'
INDEX_TAG = 'HIGH_QUALITY'
SLEEP_BETWEEN = 0.25
MARKET_CLOSE = (15, 30)

DRY_RUN = '--dry-run' in sys.argv
INCLUDE_TODAY = '--include-today' in sys.argv

# (screener name, csv symbol, yahoo ticker, company)
UNIVERSE = [
    ('Colgate-Palmoliv',        'COLPAL',       'COLPAL.NS',       'Colgate-Palmolive (India) Limited'),
    ('Sanofi Consumer',         'SANOFICONR',   'SANOFICONR.NS',   'Sanofi Consumer Healthcare India Limited'),
    ('Waaree Renewab.',         'WAAREERTL',    'WAAREERTL.NS',    'Waaree Renewable Technologies Limited'),
    ('Hindustan Zinc',          'HINDZINC',     'HINDZINC.NS',     'Hindustan Zinc Limited'),
    ('Websol Energy',           'WEBELSOLAR',   'WEBELSOLAR.NS',   'Websol Energy System Limited'),
    ('HBL Engineering',         'HBLENGINE',    'HBLENGINE.NS',    'HBL Engineering Limited'),
    ('Swaraj Engines',          'SWARAJENG',    'SWARAJENG.NS',    'Swaraj Engines Limited'),
    ('SBI Funds Mgt.',          'SBIFUNDS',     'SBIFUNDS.NS',     'SBI Funds Management Limited'),
    ('Crizac',                  'CRIZAC',       'CRIZAC.NS',       'Crizac Limited'),
    ('I R C T C',               'IRCTC',        'IRCTC.NS',        'Indian Railway Catering & Tourism Corporation Limited'),
    ('Oracle Fin.Serv.',        'OFSS',         'OFSS.NS',         'Oracle Financial Services Software Limited'),
    ('Emmvee Photovol.',        'EMMVEE',       'EMMVEE.NS',       'Emmvee Photovoltaic Power Limited'),
    ('Garden Reach Sh.',        'GRSE',         'GRSE.NS',         'Garden Reach Shipbuilders & Engineers Limited'),
    ('Travel Food',             'TRAVELFOOD',   'TRAVELFOOD.NS',   'Travel Food Services Limited'),
    ('Garuda Cons',             'GARUDA',       'GARUDA.NS',       'Garuda Construction and Engineering Limited'),
    ('Hawkins Cookers',         'HAWKINCOOK',   'HAWKINCOOK.NS',   'Hawkins Cookers Limited'),
    ('GK Energy',               'GKENERGY',     'GKENERGY.NS',     'GK Energy Limited'),
    ('Canara Robeco',           'CRAMC',        'CRAMC.NS',        'Canara Robeco Asset Management Company Limited'),
    ('Oriana Power Ltd',        'ORIANA',       'ORIANA.NS',       'Oriana Power Limited'),
    ('Natl. Aluminium',         'NATIONALUM',   'NATIONALUM.NS',   'National Aluminium Company Limited'),
    ('D.P. Abhushan',           'DPABHUSHAN',   'DPABHUSHAN.NS',   'D. P. Abhushan Limited'),
    ('Bondada Engineer',        'BONDADA',      'BONDADA.BO',      'Bondada Engineering Limited'),
    ('K.P. Energy',             'KPEL',         'KPEL.NS',         'K.P. Energy Limited'),
    ('Shankara Buildpro',       'SHANKARA',     'SHANKARA.NS',     'Shankara Building Products Limited'),
    ('Motherson Wiring',        'MSUMI',        'MSUMI.NS',        'Motherson Sumi Wiring India Limited'),
    ('Waaree Energies',         'WAAREEENER',   'WAAREEENER.NS',   'Waaree Energies Limited'),
    ('MPS',                     'MPSLTD',       'MPSLTD.NS',       'MPS Limited'),
    ('Euro Pratik Sale',        'EUROPRATIK',   'EUROPRATIK.NS',   'Euro Pratik Sales Limited'),
    ('Central Mine Pla',        'CMPDI',        'CMPDI.NS',        'Central Mine Planning & Design Institute Limited'),
    ('Inventurus Knowl',        'IKS',          'IKS.NS',          'Inventurus Knowledge Solutions Limited'),
    ('Gokul Agro',              'GOKULAGRO',    'GOKULAGRO.NS',    'Gokul Agro Resources Limited'),
    ('Force Motors',            'FORCEMOT',     'FORCEMOT.NS',     'Force Motors Limited'),
    ('Tata Motors',             'TMCV',         'TMCV.NS',         'Tata Motors Limited'),
    ('Fujiyama Power',          'UTLSOLAR',     'UTLSOLAR.NS',     'Fujiyama Power Systems Limited'),
    ('C P C L',                 'CHENNPETRO',   'CHENNPETRO.NS',   'Chennai Petroleum Corporation Limited'),
    ('Khazanchi Jewell',        'KHAZANCHI',    'KHAZANCHI.BO',    'Khazanchi Jewellers Limited'),
    ('eClerx Services',         'ECLERX',       'ECLERX.NS',       'eClerx Services Limited'),
    ('Knack Packaging',         'KNACK',        'KNACK.NS',        'Knack Packaging Limited'),
    ('Afcom Holdings',          'AFCOM',        'AFCOM.BO',        'Afcom Holdings Limited'),
    ('Premier Energies',        'PREMIERENE',   'PREMIERENE.NS',   'Premier Energies Limited'),
    ('The Bombay Burmah',       'BBTC',         'BBTC.NS',         'The Bombay Burmah Trading Corporation Limited'),
    ('Cemindia Project',        'CEMPRO',       'CEMPRO.NS',       'Cemindia Projects Limited'),
    ('CRISIL',                  'CRISIL',       'CRISIL.NS',       'CRISIL Limited'),
    ('Steelcast',               'STEELCAS',     'STEELCAS.NS',     'Steelcast Limited'),
    ('Aditya AMC',              'ABSLAMC',      'ABSLAMC.NS',      'Aditya Birla Sun Life AMC Limited'),
    ('Action Const.Eq.',        'ACE',          'ACE.NS',          'Action Construction Equipment Limited'),
    ('Krishna Defence',         'KRISHNADEF',   'KRISHNADEF.NS',   'Krishna Defence and Allied Industries Limited'),
    ('DDev Plastiks',           'DDEVPLSTIK',   'DDEVPLSTIK.NS',   'Ddev Plastiks Industries Limited'),
    ('Banco Products',          'BANCOINDIA',   'BANCOINDIA.NS',   'Banco Products (India) Limited'),
    ('Kirl.Pneumatic',          'KIRLPNU',      'KIRLPNU.NS',      'Kirloskar Pneumatic Company Limited'),
    ('MSTC',                    'MSTCLTD',      'MSTCLTD.NS',      'MSTC Limited'),
    ('Tata Elxsi',              'TATAELXSI',    'TATAELXSI.NS',    'Tata Elxsi Limited'),
    ('Lupin',                   'LUPIN',        'LUPIN.NS',        'Lupin Limited'),
    ('LTM',                     'LTM',          'LTM.NS',          'LTM Limited'),
    ('BLS Internat.',           'BLS',          'BLS.NS',          'BLS International Services Limited'),
    ('NBCC',                    'NBCC',         'NBCC.NS',         'NBCC (India) Limited'),
    ('InfoBeans Tech.',         'INFOBEAN',     'INFOBEAN.NS',     'InfoBeans Technologies Limited'),
    ('Transrail Light',         'TRANSRAILL',   'TRANSRAILL.NS',   'Transrail Lighting Limited'),
    ('Bayer Crop Sci.',         'BAYERCROP',    'BAYERCROP.NS',    'Bayer CropScience Limited'),
    ('Carraro India',           'CARRARO',      'CARRARO.NS',      'Carraro India Limited'),
    ('Bajaj Auto',              'BAJAJ-AUTO',   'BAJAJ-AUTO.NS',   'Bajaj Auto Limited'),
    ('Indiamart Inter.',        'INDIAMART',    'INDIAMART.NS',    'IndiaMART InterMESH Limited'),
    ('Seshaasai Tech.',         'STYL',         'STYL.NS',         'Seshaasai Technologies Limited'),
    ('NMDC',                    'NMDC',         'NMDC.NS',         'NMDC Limited'),
    ('Gulf Oil Lubric.',        'GULFOILLUB',   'GULFOILLUB.NS',   'Gulf Oil Lubricants India Limited'),
    ('Sky Gold & Diam.',        'SKYGOLD',      'SKYGOLD.NS',      'Sky Gold and Diamonds Limited'),
    ('Syncom Formul.',          'SYNCOMF',      'SYNCOMF.NS',      'Syncom Formulations (India) Limited'),
    ('Shringar House',          'SHRINGARMS',   'SHRINGARMS.NS',   'Shringar House of Mangalsutra Limited'),
    ('L&T Technology',          'LTTS',         'LTTS.NS',         'L&T Technology Services Limited'),
    ('Borosil Renew.',          'BORORENEW',    'BORORENEW.NS',    'Borosil Renewables Limited'),
    ('Stylam Industrie',        'STYLAMIND',    'STYLAMIND.NS',    'Stylam Industries Limited'),
    ('Tanla Platforms',         'TANLA',        'TANLA.NS',        'Tanla Platforms Limited'),
    ('Dynamic Cables',          'DYCL',         'DYCL.NS',         'Dynamic Cables Limited'),
    ('KMC Speciality',          'KMCSHIL',      'KMCSHIL.NS',      'KMC Speciality Hospitals (India) Limited'),
    ('RPG LifeScience.',        'RPGLIFE',      'RPGLIFE.NS',      'RPG Life Sciences Limited'),
    ('Jain Resource',           'JAINREC',      'JAINREC.NS',      'Jain Resource Recycling Limited'),
    ('Vimta Labs',              'VIMTALABS',    'VIMTALABS.NS',    'Vimta Labs Limited'),
    ('Chambal Fert.',           'CHAMBLFERT',   'CHAMBLFERT.NS',   'Chambal Fertilisers and Chemicals Limited'),
    ('Pricol Ltd',              'PRICOLLTD',    'PRICOLLTD.NS',    'Pricol Limited'),
    ('Sandur Manganese',        'SANDUMA',      'SANDUMA.NS',      'The Sandur Manganese & Iron Ores Limited'),
    ('Veedol Corporat',         'VEEDOL',       'VEEDOL.NS',       'Veedol Corporation Limited'),
    ('Emcure Pharma',           'EMCURE',       'EMCURE.NS',       'Emcure Pharmaceuticals Limited'),
    ('Goldiam Intl.',           'GOLDIAM',      'GOLDIAM.NS',      'Goldiam International Limited'),
    ('Ajax Engineering',        'AJAXENGG',     'AJAXENGG.NS',     'Ajax Engineering Limited'),
    ('Bhansali Engg.',          'BEPL',         'BEPL.NS',         'Bhansali Engineering Polymers Limited'),
    ('Shakti Pumps',            'SHAKTIPUMP',   'SHAKTIPUMP.NS',   'Shakti Pumps (India) Limited'),
    ('Volt.Transform.',         'VOLTAMP',      'VOLTAMP.NS',      'Voltamp Transformers Limited'),
    ('Kajaria Ceramics',        'KAJARIACER',   'KAJARIACER.NS',   'Kajaria Ceramics Limited'),
    ('Kingfa Science',          'KINGFA',       'KINGFA.NS',       'Kingfa Science & Technology (India) Limited'),
    ('Tech Mahindra',           'TECHM',        'TECHM.NS',        'Tech Mahindra Limited'),
    ('M & B Engineer.',         'MBEL',         'MBEL.NS',         'M & B Engineering Limited'),
    ('Welspun Corp',            'WELCORP',      'WELCORP.NS',      'Welspun Corp Limited'),
    ('Railtel Corpn.',          'RAILTEL',      'RAILTEL.NS',      'RailTel Corporation of India Limited'),
    ('Zensar Tech.',            'ZENSARTECH',   'ZENSARTECH.NS',   'Zensar Technologies Limited'),
    ('Petronet LNG',            'PETRONET',     'PETRONET.NS',     'Petronet LNG Limited'),
    ('Ador Welding',            'ADOR',         'ADOR.NS',         'Ador Welding Limited'),
    ('Mphasis',                 'MPHASIS',      'MPHASIS.NS',      'Mphasis Limited'),
    ('Coromandel Inter',        'COROMANDEL',   'COROMANDEL.NS',   'Coromandel International Limited'),
    ('Rites',                   'RITES',        'RITES.NS',        'RITES Limited'),
    ('PNGS Reva Diamo.',        'PNGSREVA',     'PNGSREVA.NS',     'PNGS Reva Diamond Jewellery Limited'),
    ('Garware Tech.',           'GARFIBRES',    'GARFIBRES.NS',    'Garware Technical Fibres Limited'),
    ('Vadilal Inds.',           'VADILALIND',   'VADILALIND.NS',   'Vadilal Industries Limited'),
    ('ADF Foods',               'ADFFOODS',     'ADFFOODS.NS',     'ADF Foods Limited'),
    ('Pix Transmission',        'PIXTRANS',     'PIXTRANS.NS',     'PIX Transmissions Limited'),
    ('Power Mech Proj.',        'POWERMECH',    'POWERMECH.NS',    'Power Mech Projects Limited'),
    ('Uniparts India',          'UNIPARTS',     'UNIPARTS.NS',     'Uniparts India Limited'),
    ('Automotive Axles',        'AUTOAXLES',    'AUTOAXLES.NS',    'Automotive Axles Limited'),
    ('Vesuvius India',          'VESUVIUS',     'VESUVIUS.NS',     'Vesuvius India Limited'),
    ('Vinati Organics',         'VINATIORGA',   'VINATIORGA.NS',   'Vinati Organics Limited'),
    ('Va Tech Wabag',           'WABAG',        'WABAG.NS',        'VA Tech Wabag Limited'),
    ('Venus Pipes',             'VENUSPIPES',   'VENUSPIPES.NS',   'Venus Pipes and Tubes Limited'),
    ('Pace Digitek',            'PACEDIGITK',   'PACEDIGITK.NS',   'Pace Digitek Limited'),
    ('Antelopus Selan',         'ANTELOPUS',    'ANTELOPUS.NS',    'Antelopus Selan Energy Limited'),
    ('Rolex Rings',             'ROLEXRINGS',   'ROLEXRINGS.NS',   'Rolex Rings Limited'),
    ('Birlasoft Ltd',           'BSOFT',        'BSOFT.NS',        'Birlasoft Limited'),
    ('Sri Lotus',               'LOTUSDEV',     'LOTUSDEV.NS',     'Sri Lotus Developers and Realty Limited'),
    ('NIIT Learning',           'NIITMTS',      'NIITMTS.NS',      'NIIT Learning Systems Limited'),
    ('Elecon Engg.Co',          'ELECON',       'ELECON.NS',       'Elecon Engineering Company Limited'),
    ('SPR Auto Technologies',   'SHRIPISTON',   'SHRIPISTON.NS',   'SPR Auto Technologies Limited'),
    ('Ashapura Minech.',        'ASHAPURMIN',   'ASHAPURMIN.NS',   'Ashapura Minechem Limited'),
    ('Vidya Wires',             'VIDYAWIRES',   'VIDYAWIRES.NS',   'Vidya Wires Limited'),
    ('Clean Science',           'CLEAN',        'CLEAN.NS',        'Clean Science and Technology Limited'),
    ('Dabur India',             'DABUR',        'DABUR.NS',        'Dabur India Limited'),
    ('Sirca Paints',            'SIRCA',        'SIRCA.NS',        'Sirca Paints India Limited'),
    ('AGI Infra',               'AGIIL',        'AGIIL.NS',        'AGI Infra Limited'),
    ('SEAMEC Ltd',              'SEAMECLTD',    'SEAMECLTD.NS',    'Seamec Limited'),
    ('Pearl Global Ind',        'PGIL',         'PGIL.NS',         'Pearl Global Industries Limited'),
    ('Anand Rathi Shar',        'ANANDRATHI',   'ANANDRATHI.NS',   'Anand Rathi Wealth Limited'),
    ('Apcotex Industri',        'APCOTEXIND',   'APCOTEXIND.NS',   'Apcotex Industries Limited'),
    ('L G Balakrishnan',        'LGBBROSLTD',   'LGBBROSLTD.NS',   'L.G. Balakrishnan & Bros Limited'),
    ('AGI Greenpac',            'AGI',          'AGI.NS',          'AGI Greenpac Limited'),
    ('Modern Insulator',        'MODERNINS',    '515008.BO',       'Modern Insulators Limited'),
    ('Arkade',                  'ARKADE',       'ARKADE.NS',       'Arkade Developers Limited'),
    ('Godrej Agrovet',          'GODREJAGRO',   'GODREJAGRO.NS',   'Godrej Agrovet Limited'),
    ('Sambhv Steel',            'SAMBHV',       'SAMBHV.NS',       'Sambhv Steel Tubes Limited'),
    ('GSP Crop Science',        'GSPCROP',      'GSPCROP.NS',      'GSP Crop Science Limited'),
    ('Wheels India',            'WHEELS',       'WHEELS.NS',       'Wheels India Limited'),
    ('Siyaram Silk',            'SIYSIL',       'SIYSIL.NS',       'Siyaram Silk Mills Limited'),
    ('Indegene',                'INDGN',        'INDGN.NS',        'Indegene Limited'),
    ('Marksans Pharma',         'MARKSANS',     'MARKSANS.NS',     'Marksans Pharma Limited'),
    ('Kaveri Seed Co.',         'KSCL',         'KSCL.NS',         'Kaveri Seed Company Limited'),
    ('Talbros Auto.',           'TALBROAUTO',   'TALBROAUTO.NS',   'Talbros Automotive Components Limited'),
    ('NESCO',                   'NESCO',        'NESCO.NS',        'Nesco Limited'),
    ('Federal-Mogul Go',        'FMGOETZE',     'FMGOETZE.NS',     'Federal-Mogul Goetze (India) Limited'),
    ('Gujarat Energy',          'GIPCL',        'GIPCL.NS',        'Gujarat Industries Power Company Limited'),
    ('Indian Metals',           'IMFA',         'IMFA.NS',         'Indian Metals and Ferro Alloys Limited'),
    ('Strides Pharma',          'STAR',         'STAR.NS',         'Strides Pharma Science Limited'),
    ('AWL Agri Busine.',        'AWL',          'AWL.NS',          'AWL Agri Business Limited'),
    ('Gallantt Ispat L',        'GALLANTT',     'GALLANTT.NS',     'Gallantt Ispat Limited'),
    ('IFB Industries',          'IFBIND',       'IFBIND.NS',       'IFB Industries Limited'),
    ('Vintage Coffee',          'VINCOFE',      'VINCOFE.NS',      'Vintage Coffee and Beverages Limited'),
    ('Kewal Kir.Cloth.',        'KKCL',         'KKCL.NS',         'Kewal Kiran Clothing Limited'),
    ('Mastek',                  'MASTEK',       'MASTEK.NS',       'Mastek Limited'),
]


def session_closed():
    now = datetime.now()
    return (now.hour, now.minute) >= MARKET_CLOSE


def download(sym, ticker, company, drop_today, today_str):
    df = yf.Ticker(ticker).history(period='max', interval='1d',
                                   auto_adjust=True, actions=True)
    if df is None or df.empty:
        return None
    lines = ['Symbol,Company,Industry,Index,Date,Open,High,Low,Close,'
             'Volume,Dividends,Stock Splits']
    for idx, r in df.iterrows():
        ds = idx.strftime(DATE_FMT)
        if drop_today and ds == today_str:
            continue
        lines.append(','.join([
            sym, company.replace(',', ''), '', INDEX_TAG, ds,
            str(r.get('Open', 0.0)), str(r.get('High', 0.0)),
            str(r.get('Low', 0.0)), str(r.get('Close', 0.0)),
            str(int(r.get('Volume', 0) or 0)),
            str(r.get('Dividends', 0.0)), str(r.get('Stock Splits', 0.0))]))
    return lines if len(lines) > 1 else None


def main():
    assert len({u[1] for u in UNIVERSE}) == len(UNIVERSE), 'duplicate symbol'
    drop_today = not (INCLUDE_TODAY or session_closed())
    today_str = datetime.today().strftime(DATE_FMT)

    print(f'[sep] target : {DST}')
    print(f'[sep] names  : {len(UNIVERSE)}')
    if drop_today:
        print(f'[sep] session open - excluding partial bar {today_str}')
    if DRY_RUN:
        for name, sym, tk, comp in UNIVERSE:
            print(f'  {name:<22} -> {sym:<12} [{tk}]  {comp}')
        print('[sep] DRY RUN - nothing written')
        return

    os.makedirs(DST, exist_ok=True)
    ok = fail = 0
    failures = []
    for i, (name, sym, ticker, company) in enumerate(UNIVERSE, 1):
        try:
            lines = download(sym, ticker, company, drop_today, today_str)
        except Exception as e:
            lines = None
            print(f'  [{i:3}/{len(UNIVERSE)}] {sym:<12} ERROR {e}')
        if not lines:
            fail += 1
            failures.append((name, sym, ticker))
            print(f'  [{i:3}/{len(UNIVERSE)}] {sym:<12} NO DATA [{ticker}]')
            continue
        with open(os.path.join(DST, sym + '.csv'), 'w', encoding='utf-8',
                  newline='') as f:
            f.write('\n'.join(lines) + '\n')
        first = lines[1].split(',')[4]
        last = lines[-1].split(',')[4]
        print(f'  [{i:3}/{len(UNIVERSE)}] {sym:<12} {len(lines)-1:>5} rows  '
              f'{first} -> {last}  [{ticker}]')
        ok += 1
        time.sleep(SLEEP_BETWEEN)

    total = len([f for f in os.listdir(DST) if f.lower().endswith('.csv')])
    print(f'\n[sep] downloaded {ok} | failed {fail}')
    print(f'[sep] {DST} now holds {total} CSVs')
    if failures:
        print('[sep] failed names:')
        for n, s, t in failures:
            print(f'      {n:<22} {s:<12} {t}')


if __name__ == '__main__':
    main()
