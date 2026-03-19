# main.py - API Python complète pour scraping ERAC sur Railway
# V3.2 - Support bilingue FR/DE pour adresses, dates, fuel, VIN

from flask import Flask, jsonify
import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime
import time
import re

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "service": "ERAC Scraper API",
        "status": "running",
        "version": "3.2",
        "endpoints": {
            "/": "GET - Informations de l'API",
            "/scrape/france": "GET - Scraping ERAC France (avec VIN)",
            "/scrape/germany": "GET - Scraping ERAC Germany (avec VIN)",
            "/scrape/germany/tenders": "GET - Scraping InTender Germany",
            "/scrape/france/tenders": "GET - Scraping InTender France",
            "/health": "GET - Status de santé",
            "/debug/movement/{id}": "GET - Debug d'un mouvement"
        }
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})


# ============================================================
# MISSIONS (INBOUND/OUTBOUND)
# ============================================================

# Clés bilingues pour la détection des sections
KEYS = {
    'collection_address': ['Collection Address', 'Adresse de la collecte'],
    'delivery_address':   ['Delivery Address',   'Adresse de livraison'],
    'collection_date':    ['Collection Date', 'Expected Collection', 'Date prévue de collecte', 'Date de collecte'],
    'delivery_date':      ['Delivery Date', 'Expected Delivery', 'Date de livraison prévue', 'Date de livraison'],
    'tel':                ['Tel No.', 'Numéro de téléphone', 'N° de téléphone', 'Phone'],
    'email':              ['Email'],
    'vin':                ['VIN', 'Vin'],
    'fuel':               ['Fuel', 'Carburant', 'Type de carburant'],
    'route':              ['Route', 'Distance', 'Estimate', 'Itinéraire'],
    'unit':               ['Unit', 'Unité'],
    'make_model':         ['Make', 'Model', 'Marque', 'Modèle'],
    'registration':       ['RegNo', 'Reg No', 'Registration', 'Immatriculation'],
}


def _find_heading(soup, keys):
    """Trouve un h2/h3 contenant l'un des mots-clés (FR ou EN)."""
    for tag in soup.find_all(['h2', 'h3', 'h4']):
        text = tag.get_text()
        if any(k in text for k in keys):
            return tag
    return None


def _extract_tel(text):
    """Extrait un numéro de téléphone depuis un texte."""
    m = re.search(r'[:\s]([\+\d][\d\s/\-\+\.]{6,})', text)
    return m.group(1).strip() if m else None


def _extract_email(text):
    """Extrait une adresse email depuis un texte."""
    m = re.search(r'Email\s*:\s*([^\s<]+)', text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _extract_date_from_text(text):
    """Extrait une date (formats DD/MM/YYYY ou YYYY-MM-DD ou DD.MM.YYYY)."""
    m = re.search(r'(\d{2}[/\.\-]\d{2}[/\.\-]\d{4}|\d{4}[/\.\-]\d{2}[/\.\-]\d{2})', text)
    return m.group(1).strip() if m else None


def _parse_address_section(heading_tag):
    """
    Parse une section adresse à partir de son h2 (FR ou EN).
    Structure réelle FR :
      div.col-xs-12
        h2 "Adresse de la collecte"
        hr
        div > h4 (nom), h4 (adresse)   ← premier div sibling
        div "Numéro de téléphone.:&nbsp;..."
        div "N° de téléphone:&nbsp;..."
        div "Email:&nbsp;..."
        div.alert ...
        div "Date prévue de collecte: ..."
        hr
        div "Special Instructions:"     ← label seul
        div style="color:red" "VALEUR"  ← valeur suivante
    """
    data = {'name': None, 'address': None, 'tel': None, 'email': None, 'special_instructions': None}

    if not heading_tag:
        return data

    # === NOM et ADRESSE : premier div sibling après le h2 ===
    first_div = heading_tag.find_next_sibling('div')
    if first_div:
        h4s = first_div.find_all('h4')
        if len(h4s) >= 1:
            name_text = h4s[0].get_text().strip()
            match = re.search(r'\(([^)]+)\)', name_text)
            code = match.group(1) if match else ''
            data['name'] = name_text.replace(f'({code})', '').strip() if code else name_text
        if len(h4s) >= 2:
            data['address'] = h4s[1].get_text().strip()

    # === Parcourir tous les div siblings directs du h2 ===
    prev_was_special_label = False

    for sibling in heading_tag.find_next_siblings():
        # Stop au prochain heading de section
        if sibling.name in ['h1', 'h2', 'h3']:
            break

        if sibling.name != 'div':
            prev_was_special_label = False
            continue

        raw = sibling.get_text(' ', strip=True).replace('\xa0', ' ').strip()
        if not raw:
            prev_was_special_label = False
            continue

        # Si le div précédent était le label "Special Instructions:"
        if prev_was_special_label and not data['special_instructions']:
            data['special_instructions'] = raw
            prev_was_special_label = False
            continue

        # Tel
        if any(k in raw for k in KEYS['tel']) and not data['tel']:
            tel = _extract_tel(raw)
            if tel:
                data['tel'] = tel

        # Email
        if 'Email' in raw and not data['email']:
            email = _extract_email(raw)
            if email:
                data['email'] = email

        # Special Instructions label
        if raw.rstrip(':').strip() in ['Special Instructions', 'Instructions spéciales', 'Instructions particulières']:
            prev_was_special_label = True
            continue

        prev_was_special_label = False

    return data




def _extract_date_field(soup, input_ids, label_keys):
    """
    Cherche une date via input id OU label FR/EN → p.form-control-static OU texte libre.
    """
    # 1. Input direct
    for id_ in input_ids:
        el = soup.find('input', {'id': id_}) or soup.find('input', {'name': id_})
        if el:
            val = el.get('value', '').strip()
            if val:
                return val

    # 2. Label → p.form-control-static
    for label in soup.find_all('label'):
        if any(k in label.get_text() for k in label_keys):
            elem = label.parent.find('p', class_='form-control-static')
            if elem:
                val = elem.get_text().strip()
                if val:
                    return val

    # 3. Chercher dans les <div> contenant le label (FR/EN) — structure France
    for div in soup.find_all('div'):
        raw = div.get_text(' ', strip=True).replace('\xa0', ' ')
        if any(k in raw for k in label_keys):
            date = _extract_date_from_text(raw)
            if date:
                return date

    # 4. Texte brut de toute la page (dernier recours)
    full_text = soup.get_text('\n')
    for line in full_text.splitlines():
        if any(k in line for k in label_keys):
            date = _extract_date_from_text(line)
            if date:
                return date

    return None


def get_mission_details(session, movement_id, country="france", headers=None, debug=False):
    try:
        movement_url = f'https://erac.hkremarketing.com/movement/{movement_id}'
        if headers is None:
            headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

        response = session.get(movement_url, headers=headers)

        if response.status_code != 200:
            return {'movement_id': movement_id, 'error': f'HTTP {response.status_code}'}

        soup = BeautifulSoup(response.text, 'html.parser')

        if debug:
            try:
                with open(f'/tmp/movement_debug_{movement_id}.html', 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print(f"HTML sauvegardé: /tmp/movement_debug_{movement_id}.html")
            except:
                pass

        movement_data = {
            'movement_id': movement_id,
            'vin': None,
            'make_model': None,
            'registration': None,
            'unit_no': None,
            'fuel_type': None,
            'route_estimate': None,
            'route_distance_km': None,
            'route_duration': None,
            'collection_date': None,
            'delivery_date': None,
            'collection_address': None,
            'delivery_address': None,
            'collection_address_full': {'name': None, 'address': None, 'tel': None, 'email': None, 'special_instructions': None},
            'delivery_address_full': {'name': None, 'address': None, 'tel': None, 'email': None, 'special_instructions': None},
            'status': None,
            'delivery_charge': None,
            'error': None
        }

        # ======================================================
        # VIN — 5 fallbacks
        # ======================================================
        # 1. label.control-label contenant VIN → p.form-control-static
        for label in soup.find_all('label', class_='control-label'):
            if 'VIN' in label.get_text().upper():
                elem = label.parent.find('p', class_='form-control-static')
                if elem:
                    movement_data['vin'] = elem.get_text().strip()
                    break

        # 2. N'importe quel label contenant VIN → next p.form-control-static
        if not movement_data['vin']:
            for label in soup.find_all('label'):
                if 'VIN' in label.get_text().strip().upper():
                    elem = label.find_next('p', class_='form-control-static')
                    if elem:
                        movement_data['vin'] = elem.get_text().strip()
                        break

        # 3. p.form-control-static dont le contenu ressemble à un VIN (17 chars)
        if not movement_data['vin']:
            for elem in soup.find_all('p', class_='form-control-static'):
                text = elem.get_text().strip().upper()
                if len(text) == 17 and text[0] in 'ZWVJLMRSTUX123456789':
                    movement_data['vin'] = text
                    break

        # 4. input id/name Vin
        if not movement_data['vin']:
            el = soup.find('input', {'id': 'Vin'}) or soup.find('input', {'name': 'Vin'})
            if el:
                movement_data['vin'] = el.get('value', '').strip()

        # 5. Regex VIN dans le texte brut
        if not movement_data['vin']:
            vin_match = re.search(r'\b([A-HJ-NPR-Z0-9]{17})\b', soup.get_text())
            if vin_match:
                movement_data['vin'] = vin_match.group(1)

        # ======================================================
        # REGISTRATION
        # ======================================================
        el = soup.find('input', {'id': 'RegNo'}) or soup.find('input', {'name': 'RegNo'})
        if el:
            movement_data['registration'] = el.get('value', '').strip()
        else:
            for label in soup.find_all('label'):
                if any(k in label.get_text() for k in KEYS['registration']):
                    elem = label.parent.find('p', class_='form-control-static')
                    if elem:
                        movement_data['registration'] = elem.get_text().strip()
                        break

        # ======================================================
        # MAKE/MODEL
        # ======================================================
        el = soup.find('input', {'id': 'MakeModel'}) or soup.find('input', {'name': 'MakeModel'})
        if el:
            movement_data['make_model'] = el.get('value', '').strip()
        else:
            for label in soup.find_all('label'):
                if any(k in label.get_text() for k in KEYS['make_model']):
                    elem = label.parent.find('p', class_='form-control-static')
                    if elem:
                        movement_data['make_model'] = elem.get_text().strip()
                        break

        # ======================================================
        # FUEL TYPE — FR/EN
        # ======================================================
        el = soup.find('input', {'id': 'FuelType'}) or soup.find('input', {'name': 'FuelType'})
        if el:
            movement_data['fuel_type'] = el.get('value', '').strip()
        else:
            sel = soup.find('select', {'id': 'FuelType'}) or soup.find('select', {'name': 'FuelType'})
            if sel:
                selected = sel.find('option', selected=True)
                if selected:
                    movement_data['fuel_type'] = selected.get_text().strip()
            else:
                for label in soup.find_all('label'):
                    if any(k in label.get_text() for k in KEYS['fuel']):
                        elem = label.parent.find('p', class_='form-control-static') or label.parent.find('span')
                        if elem:
                            movement_data['fuel_type'] = elem.get_text().strip()
                            break

        # ======================================================
        # ROUTE ESTIMATE
        # ======================================================
        el = soup.find('input', {'id': 'RouteEstimate'}) or soup.find('input', {'name': 'RouteEstimate'})
        if el:
            movement_data['route_estimate'] = el.get('value', '').strip()
        else:
            for label in soup.find_all('label'):
                if any(k in label.get_text() for k in KEYS['route']):
                    elem = label.parent.find('p', class_='form-control-static') or label.parent.find('span')
                    if elem:
                        movement_data['route_estimate'] = elem.get_text().strip()
                        break

        if movement_data['route_estimate']:
            dist_m = re.search(r'([\d,\.]+)\s*km', movement_data['route_estimate'])
            if dist_m:
                movement_data['route_distance_km'] = float(dist_m.group(1).replace(',', '.'))
            dur_m = re.search(r'(\d+h\s*\d*m?)', movement_data['route_estimate'])
            if dur_m:
                movement_data['route_duration'] = dur_m.group(1).strip()

        # ======================================================
        # UNIT NO
        # ======================================================
        el = soup.find('input', {'id': 'UnitNo'}) or soup.find('input', {'name': 'UnitNo'})
        if el:
            movement_data['unit_no'] = el.get('value', '').strip()
        else:
            for label in soup.find_all('label'):
                if any(k in label.get_text() for k in KEYS['unit']):
                    elem = label.parent.find('p', class_='form-control-static')
                    if elem:
                        movement_data['unit_no'] = elem.get_text().strip()
                        break

        # ======================================================
        # DATES — FR/EN
        # ======================================================
        movement_data['collection_date'] = _extract_date_field(
            soup,
            input_ids=['CollectionDate'],
            label_keys=KEYS['collection_date']
        )
        movement_data['delivery_date'] = _extract_date_field(
            soup,
            input_ids=['DeliveryDate'],
            label_keys=KEYS['delivery_date']
        )

        # ======================================================
        # ADRESSES — FR/EN via heading bilingue
        # ======================================================
        coll_heading = _find_heading(soup, KEYS['collection_address'])
        movement_data['collection_address_full'] = _parse_address_section(coll_heading)

        deliv_heading = _find_heading(soup, KEYS['delivery_address'])
        movement_data['delivery_address_full'] = _parse_address_section(deliv_heading)

        # Champs plats pour compatibilité
        movement_data['collection_address'] = movement_data['collection_address_full'].get('address')
        movement_data['delivery_address'] = movement_data['delivery_address_full'].get('address')

        # ======================================================
        # DELIVERY CHARGE
        # ======================================================
        el = soup.find('input', {'id': 'DeliveryCharge'}) or soup.find('input', {'name': 'DeliveryCharge'})
        if el:
            movement_data['delivery_charge'] = el.get('value', '').strip()

        if debug:
            print(f"  VIN:      {movement_data['vin']}")
            print(f"  Fuel:     {movement_data['fuel_type']}")
            print(f"  CollDate: {movement_data['collection_date']}")
            print(f"  DelDate:  {movement_data['delivery_date']}")
            print(f"  CollAddr: {movement_data['collection_address_full']}")
            print(f"  DelAddr:  {movement_data['delivery_address_full']}")

        return movement_data

    except Exception as e:
        return {'movement_id': movement_id, 'error': str(e)}


def enrich_missions_with_details(session, missions, country="france", headers=None, delay=0.3):
    enriched = []
    total = len(missions)
    for idx, mission in enumerate(missions):
        percent = int((idx + 1) / total * 100)
        print(f"[{percent}%] {idx+1}/{total} - {mission.get('RegNo', 'N/A')}")

        movement_id = mission.get('Id')
        if movement_id:
            details = get_mission_details(session, movement_id, country, headers, debug=(idx == 0))
            enriched_mission = {**mission, **details}
            if details.get('vin'):        print(f"     VIN:  {details['vin']}")
            if details.get('fuel_type'):  print(f"     Fuel: {details['fuel_type']}")
            if details.get('route_estimate'): print(f"     Route: {details['route_estimate']}")
        else:
            enriched_mission = mission

        enriched.append(enriched_mission)
        if idx < total - 1:
            time.sleep(delay)

    print(f"Enrichissement termine: {total} missions")
    return enriched


def scrape_erac_country(country="france", enrich_details=True):
    try:
        print(f"Debut scraping ERAC {country.upper()}...")

        if country.lower() == "germany":
            login_id = os.getenv('ERAC_GERMANY_LOGIN')
            password = os.getenv('ERAC_GERMANY_PASSWORD')
        else:
            login_id = os.getenv('ERAC_FRANCE_LOGIN')
            password = os.getenv('ERAC_FRANCE_PASSWORD')

        if not login_id or not password:
            raise ValueError(f"Variables d'env manquantes pour {country.upper()}")

        session = requests.Session()
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }

        login_page_response = session.get(
            'https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound', headers=headers)
        login_page_soup = BeautifulSoup(login_page_response.text, 'html.parser')
        token_element = login_page_soup.find('input', {'name': '__RequestVerificationToken'})
        if not token_element:
            raise ValueError("Token de verification non trouve")
        token = token_element['value']

        login_payload = {'LoginId': login_id, 'Password': password, '__RequestVerificationToken': token}
        login_headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        login_headers.update(headers)

        session.post('https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound',
                     data=login_payload, headers=login_headers)
        session.post('https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FInbound',
                     data=login_payload, headers=login_headers)

        terms_page_response = session.get('https://erac.hkremarketing.com/vendor/scoc', headers=headers)
        terms_page_soup = BeautifulSoup(terms_page_response.text, 'html.parser')
        token_element = terms_page_soup.find('input', {'name': '__RequestVerificationToken'})
        accept_payload = {'action': 'agree'}
        if token_element:
            accept_payload['__RequestVerificationToken'] = token_element['value']
        accept_headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        accept_headers.update(headers)
        session.post('https://erac.hkremarketing.com/vendor/scoc', data=accept_payload, headers=accept_headers)

        ajax_headers = {'Accept': 'application/json, text/javascript, */*; q=0.01', 'X-Requested-With': 'XMLHttpRequest'}
        ajax_headers.update(headers)

        ajax_payload_outbound = {
            'draw': 2,
            'columns[0][data]': 'GroupCode', 'columns[0][name]': '', 'columns[0][searchable]': 'true', 'columns[0][orderable]': 'true', 'columns[0][search][value]': '', 'columns[0][search][regex]': 'false',
            'columns[1][data]': 'RegNo', 'columns[1][name]': '', 'columns[1][searchable]': 'true', 'columns[1][orderable]': 'true', 'columns[1][search][value]': '', 'columns[1][search][regex]': 'false',
            'columns[2][data]': 'UnitNo', 'columns[2][name]': '', 'columns[2][searchable]': 'true', 'columns[2][orderable]': 'true', 'columns[2][search][value]': '', 'columns[2][search][regex]': 'false',
            'columns[3][data]': 'MakeModel', 'columns[3][name]': '', 'columns[3][searchable]': 'true', 'columns[3][orderable]': 'true', 'columns[3][search][value]': '', 'columns[3][search][regex]': 'false',
            'columns[4][data]': 'DeliveryCharge', 'columns[4][name]': '', 'columns[4][searchable]': 'true', 'columns[4][orderable]': 'true', 'columns[4][search][value]': '', 'columns[4][search][regex]': 'false',
            'columns[5][data]': 'AllocationDate', 'columns[5][name]': '', 'columns[5][searchable]': 'true', 'columns[5][orderable]': 'true', 'columns[5][search][value]': '', 'columns[5][search][regex]': 'false',
            'columns[6][data]': 'AllocationDateTicks', 'columns[6][name]': '', 'columns[6][searchable]': 'true', 'columns[6][orderable]': 'true', 'columns[6][search][value]': '', 'columns[6][search][regex]': 'false',
            'columns[7][data]': 'CollectionAddress', 'columns[7][name]': '', 'columns[7][searchable]': 'true', 'columns[7][orderable]': 'true', 'columns[7][search][value]': '', 'columns[7][search][regex]': 'false',
            'columns[8][data]': 'ExpectedDeliveryDate', 'columns[8][name]': '', 'columns[8][searchable]': 'true', 'columns[8][orderable]': 'true', 'columns[8][search][value]': '', 'columns[8][search][regex]': 'false',
            'columns[9][data]': 'ExpectedDeliveryDateTicks', 'columns[9][name]': '', 'columns[9][searchable]': 'true', 'columns[9][orderable]': 'true', 'columns[9][search][value]': '', 'columns[9][search][regex]': 'false',
            'columns[10][data]': 'DeliveryAddress', 'columns[10][name]': '', 'columns[10][searchable]': 'true', 'columns[10][orderable]': 'true', 'columns[10][search][value]': '', 'columns[10][search][regex]': 'false',
            'order[0][column]': 0, 'order[0][dir]': 'asc',
            'start': 0, 'length': 500,
            'search[value]': '', 'search[regex]': 'false',
            'Code': 'outbound', 'MovementType': 'collections',
            'RegNo': '', 'CollectionDateFrom': '', 'CollectionDateTo': '', 'CollectionPostcode': '',
            'DeliveryDateFrom': '', 'DeliveryDateTo': '', 'DeliveryPostcode': '',
            'CreatedDateFrom': '', 'CreatedDateTo': '', 'ReleaseCode': ''
        }

        ajax_payload_inbound = dict(ajax_payload_outbound)
        ajax_payload_inbound['Code'] = 'inbound'

        ajax_response_inbound = session.post('https://erac.hkremarketing.com/Vendor/AjaxSearch',
                                             data=ajax_payload_inbound, headers=ajax_headers)
        ajax_response_outbound = session.post('https://erac.hkremarketing.com/Vendor/AjaxSearch',
                                              data=ajax_payload_outbound, headers=ajax_headers)

        data_inbound = ajax_response_inbound.json()
        data_outbound = ajax_response_outbound.json()

        if enrich_details:
            enriched_inbound = enrich_missions_with_details(session, data_inbound['data'], country, ajax_headers, delay=0.3)
            enriched_outbound = enrich_missions_with_details(session, data_outbound['data'], country, ajax_headers, delay=0.3)
        else:
            enriched_inbound = data_inbound['data']
            enriched_outbound = data_outbound['data']

        return {
            'country': country.upper(),
            'inbound': enriched_inbound,
            'outbound': enriched_outbound,
            'timestamp': datetime.utcnow().isoformat(),
            'total_inbound': len(enriched_inbound),
            'total_outbound': len(enriched_outbound),
            'records_total_inbound': data_inbound.get('recordsTotal', 0),
            'records_total_outbound': data_outbound.get('recordsTotal', 0),
            'enriched': enrich_details
        }
    except Exception as e:
        print(f"Erreur scraping {country.upper()}: {str(e)}")
        raise


# ============================================================
# ENDPOINTS MISSIONS
# ============================================================

@app.route('/scrape/france')
def scrape_france():
    try:
        data = scrape_erac_country("france", enrich_details=True)
        return jsonify({'success': True, 'data': data,
                        'message': f"Scraping FRANCE: {data['total_outbound']} outbound, {data['total_inbound']} inbound"})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'country': 'FRANCE',
                        'timestamp': datetime.utcnow().isoformat()}), 500


@app.route('/scrape/germany')
def scrape_germany():
    try:
        data = scrape_erac_country("germany", enrich_details=True)
        return jsonify({'success': True, 'data': data,
                        'message': f"Scraping GERMANY: {data['total_outbound']} outbound, {data['total_inbound']} inbound"})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'country': 'GERMANY',
                        'timestamp': datetime.utcnow().isoformat()}), 500


@app.route('/debug/movement/<movement_id>')
def debug_movement(movement_id):
    try:
        login_id = os.getenv('ERAC_GERMANY_LOGIN')
        password = os.getenv('ERAC_GERMANY_PASSWORD')
        if not login_id or not password:
            return jsonify({'success': False, 'error': 'Env vars manquantes'}), 500

        headers = {'Accept': 'text/html,*/*;q=0.8', 'User-Agent': 'Mozilla/5.0'}
        session = requests.Session()

        login_page = session.get(
            'https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound', headers=headers)
        soup = BeautifulSoup(login_page.text, 'html.parser')
        token = soup.find('input', {'name': '__RequestVerificationToken'})['value']

        login_headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        login_headers.update(headers)
        session.post('https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound',
                     data={'LoginId': login_id, 'Password': password, '__RequestVerificationToken': token},
                     headers=login_headers)

        details = get_mission_details(session, movement_id, "germany", headers, debug=True)
        return jsonify({'success': True, 'movement_id': movement_id, 'details': details})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# INTENDER
# ============================================================

def erac_login_for_tender(country="germany"):
    if country.lower() == "germany":
        login_id = os.getenv('ERAC_GERMANY_LOGIN')
        password = os.getenv('ERAC_GERMANY_PASSWORD')
    else:
        login_id = os.getenv('ERAC_FRANCE_LOGIN')
        password = os.getenv('ERAC_FRANCE_PASSWORD')

    if not login_id or not password:
        raise ValueError(f"Env vars manquantes pour {country.upper()}")

    session = requests.Session()
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
        'Connection': 'keep-alive',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }

    login_page = session.get(
        'https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound', headers=headers)
    soup = BeautifulSoup(login_page.text, 'html.parser')
    token_el = soup.find('input', {'name': '__RequestVerificationToken'})
    if not token_el:
        raise ValueError("Token non trouve")
    token = token_el['value']

    login_payload = {'LoginId': login_id, 'Password': password, '__RequestVerificationToken': token}
    login_headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    login_headers.update(headers)

    session.post('https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound',
                 data=login_payload, headers=login_headers)
    session.post('https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FInbound',
                 data=login_payload, headers=login_headers)

    terms_page = session.get('https://erac.hkremarketing.com/vendor/scoc', headers=headers)
    terms_soup = BeautifulSoup(terms_page.text, 'html.parser')
    token_el = terms_soup.find('input', {'name': '__RequestVerificationToken'})
    accept_payload = {'action': 'agree'}
    if token_el:
        accept_payload['__RequestVerificationToken'] = token_el['value']
    accept_headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    accept_headers.update(headers)
    session.post('https://erac.hkremarketing.com/vendor/scoc', data=accept_payload, headers=accept_headers)

    return session, headers


def parse_tender_vehicles(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    vehicles = []

    tender_meta = {}
    for field_id in ['EndDate', 'EndDateTicks', 'ServerTicks', 'Currency', 'IsActive', 'OnHold']:
        el = soup.find('input', {'id': field_id})
        tender_meta[field_id.lower()] = el.get('value', '').strip() if el else None

    table = soup.find('table', {'id': 'tblVehicles'})
    if not table:
        return {'meta': tender_meta, 'vehicles': [], 'count': 0}

    tbody = table.find('tbody')
    rows = tbody.find_all('tr') if tbody else []

    for idx, row in enumerate(rows):
        vehicle = parse_tender_row(row, idx)
        if vehicle:
            vehicles.append(vehicle)

    return {'meta': tender_meta, 'vehicles': vehicles, 'count': len(vehicles)}


def parse_tender_row(row, idx):
    try:
        cells = row.find_all('td')
        num_cols = len(cells)
        if num_cols < 13:
            return None

        has_desired_dates = num_cols >= 16

        tender_vehicle_id_el = row.find('input', {'name': re.compile(r'Vehicles\[\d+\]\.TenderVehicleId')})
        tender_vehicle_id = tender_vehicle_id_el.get('value', '') if tender_vehicle_id_el else None

        link_move_el = cells[0].find('input')
        link_move = link_move_el.get('value', '').strip() if link_move_el else ''

        make_model = re.sub(r'\s+', ' ', cells[1].get_text(separator=' ', strip=True)).strip()

        vehicle_type_raw = cells[2].get_text(separator='|', strip=True)
        vt_parts = vehicle_type_raw.split('|')
        vehicle_type = vt_parts[0].strip() if len(vt_parts) > 0 else ''
        fuel_type = vt_parts[1].strip() if len(vt_parts) > 1 else ''

        collection_code = cells[3].get_text(strip=True)
        collection_town = cells[4].get_text(strip=True)
        collection_post_code = cells[5].get_text(strip=True)
        delivery_code = cells[6].get_text(strip=True)
        delivery_town = cells[7].get_text(strip=True)
        delivery_post_code = cells[8].get_text(strip=True)

        del_date_el = cells[9].find('input')
        existing_delivery_date = del_date_el.get('value', '').strip() if del_date_el else ''

        charge_el = cells[10].find('input')
        existing_charge = charge_el.get('value', '').strip() if charge_el else ''

        service_el = cells[11].find('select')
        service_type = ''
        service_options = []
        if service_el:
            selected = service_el.find('option', selected=True)
            service_type = selected.get('value', '') if selected else ''
            for opt in service_el.find_all('option'):
                service_options.append({
                    'value': opt.get('value', ''),
                    'label': opt.get_text(strip=True),
                    'selected': opt.has_attr('selected')
                })

        route_estimate = cells[12].get_text(strip=True) if num_cols > 12 else ''
        route_distance_km = None
        route_duration = None
        if route_estimate:
            dist_match = re.search(r'([\d,\.]+)\s*km', route_estimate)
            if dist_match:
                route_distance_km = float(dist_match.group(1).replace(',', '.'))
            dur_match = re.search(r'(\d+h\s*\d*m?)', route_estimate)
            if dur_match:
                route_duration = dur_match.group(1).strip()

        desired_collect_date = ''
        desired_delivery_date = ''
        special_instructions = ''

        if has_desired_dates:
            desired_collect_date = cells[13].get_text(strip=True) if num_cols > 13 else ''
            desired_delivery_date = cells[14].get_text(strip=True) if num_cols > 14 else ''
            special_instructions = cells[15].get_text(strip=True) if num_cols > 15 else ''
        else:
            special_instructions = cells[13].get_text(strip=True) if num_cols > 13 else ''

        needs_trailer = bool(re.search(r'needs?\s+trailer|sur\s+camion', special_instructions, re.IGNORECASE))

        return {
            'tender_vehicle_id': tender_vehicle_id,
            'vehicle_index': idx,
            'make_model': make_model,
            'vehicle_type': vehicle_type,
            'fuel_type': fuel_type,
            'collection_code': collection_code,
            'collection_town': collection_town,
            'collection_post_code': collection_post_code,
            'delivery_code': delivery_code,
            'delivery_town': delivery_town,
            'delivery_post_code': delivery_post_code,
            'route_estimate_raw': route_estimate,
            'route_distance_km': route_distance_km,
            'route_duration': route_duration,
            'desired_collect_date': desired_collect_date,
            'desired_delivery_date': desired_delivery_date,
            'existing_charge': existing_charge,
            'existing_delivery_date': existing_delivery_date,
            'service_type': service_type,
            'service_options': service_options,
            'special_instructions': special_instructions,
            'needs_trailer': needs_trailer,
            'link_move': link_move
        }
    except Exception as e:
        print(f"Erreur parsing row {idx}: {str(e)}")
        return None


def scrape_intender(country="germany"):
    try:
        session, headers = erac_login_for_tender(country)

        tender_response = session.get('https://erac.hkremarketing.com/Vendor/Tender/InTender', headers=headers)

        if tender_response.status_code != 200:
            raise ValueError(f"HTTP {tender_response.status_code}")

        html_text = tender_response.text
        has_table = 'tblVehicles' in html_text
        has_login = 'LoginId' in html_text
        has_closed = 'Closed' in html_text

        if has_login and not has_table:
            raise ValueError("Session expiree")

        if not has_table:
            status = 'no_active_tender' if has_closed else 'unexpected_page'
            return {'country': country.upper(), 'status': status, 'vehicles': [], 'count': 0,
                    'timestamp': datetime.utcnow().isoformat()}

        result = parse_tender_vehicles(html_text)
        result['country'] = country.upper()
        result['status'] = 'active'
        result['timestamp'] = datetime.utcnow().isoformat()

        return result
    except Exception as e:
        print(f"Erreur InTender: {str(e)}")
        raise


@app.route('/scrape/germany/tenders')
def scrape_germany_tenders():
    try:
        data = scrape_intender("germany")
        return jsonify({'success': True, 'data': data, 'message': f"InTender GERMANY: {data['count']} vehicules"})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'country': 'GERMANY',
                        'timestamp': datetime.utcnow().isoformat()}), 500


@app.route('/scrape/france/tenders')
def scrape_france_tenders():
    try:
        data = scrape_intender("france")
        return jsonify({'success': True, 'data': data, 'message': f"InTender FRANCE: {data['count']} vehicules"})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'country': 'FRANCE',
                        'timestamp': datetime.utcnow().isoformat()}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5030))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    print(f"ERAC Scraper v3.2 sur port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
