# main.py - API Python complète pour scraping ERAC sur Railway
# V3.1 - Ajout fuel_type + route_estimate dans les missions + InTender

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
        "version": "3.1",
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

def get_mission_details(session, movement_id, country="france", headers=None, debug=False):
    try:
        movement_url = f'https://erac.hkremarketing.com/movement/{movement_id}'
        if headers is None:
            headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
        
        response = session.get(movement_url, headers=headers)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            if debug:
                try:
                    with open(f'/tmp/movement_debug_{movement_id}.html', 'w', encoding='utf-8') as f:
                        f.write(response.text)
                except: pass
            
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
                'collection_address_full': {'name': None, 'address': None, 'tel': None, 'email': None},
                'delivery_address_full': {'name': None, 'address': None, 'tel': None, 'email': None},
                'status': None,
                'delivery_charge': None,
                'error': None
            }
            
            # === VIN ===
            labels = soup.find_all('label', class_='control-label')
            for label in labels:
                if 'VIN' in label.get_text().upper():
                    parent = label.parent
                    vin_element = parent.find('p', class_='form-control-static')
                    if vin_element:
                        movement_data['vin'] = vin_element.get_text().strip()
                        break
            
            if not movement_data['vin']:
                all_labels = soup.find_all('label')
                for label in all_labels:
                    if 'VIN' in label.get_text().strip().upper():
                        next_elem = label.find_next('p', class_='form-control-static')
                        if next_elem:
                            movement_data['vin'] = next_elem.get_text().strip()
                            break
            
            if not movement_data['vin']:
                for elem in soup.find_all('p', class_='form-control-static'):
                    text = elem.get_text().strip().upper()
                    if len(text) == 17 and text[0] in 'ZWVJLMRSTUX123456789':
                        movement_data['vin'] = text
                        break
            
            if not movement_data['vin']:
                vin_el = soup.find('input', {'id': 'Vin'}) or soup.find('input', {'name': 'Vin'})
                if vin_el:
                    movement_data['vin'] = vin_el.get('value', '').strip()
            
            # === REGISTRATION ===
            reg_el = soup.find('input', {'id': 'RegNo'}) or soup.find('input', {'name': 'RegNo'})
            if reg_el:
                movement_data['registration'] = reg_el.get('value', '').strip()
            else:
                for label in soup.find_all('label'):
                    if any(k in label.get_text() for k in ['RegNo', 'Reg No', 'Registration']):
                        elem = label.parent.find('p', class_='form-control-static')
                        if elem:
                            movement_data['registration'] = elem.get_text().strip()
                            break
            
            # === MAKE/MODEL ===
            make_el = soup.find('input', {'id': 'MakeModel'}) or soup.find('input', {'name': 'MakeModel'})
            if make_el:
                movement_data['make_model'] = make_el.get('value', '').strip()
            else:
                for label in soup.find_all('label'):
                    if 'Make' in label.get_text() or 'Model' in label.get_text():
                        elem = label.parent.find('p', class_='form-control-static')
                        if elem:
                            movement_data['make_model'] = elem.get_text().strip()
                            break
            
            # === FUEL TYPE ===
            fuel_el = soup.find('input', {'id': 'FuelType'}) or soup.find('input', {'name': 'FuelType'})
            if fuel_el:
                movement_data['fuel_type'] = fuel_el.get('value', '').strip()
            else:
                fuel_select = soup.find('select', {'id': 'FuelType'}) or soup.find('select', {'name': 'FuelType'})
                if fuel_select:
                    selected = fuel_select.find('option', selected=True)
                    if selected:
                        movement_data['fuel_type'] = selected.get_text().strip()
                else:
                    for label in soup.find_all('label'):
                        label_text = label.get_text().strip()
                        if 'Fuel' in label_text:
                            parent = label.parent
                            elem = parent.find('p', class_='form-control-static') or parent.find('span')
                            if elem:
                                movement_data['fuel_type'] = elem.get_text().strip()
                                break
            
            # === ROUTE ESTIMATE ===
            route_el = soup.find('input', {'id': 'RouteEstimate'}) or soup.find('input', {'name': 'RouteEstimate'})
            if route_el:
                movement_data['route_estimate'] = route_el.get('value', '').strip()
            else:
                for label in soup.find_all('label'):
                    label_text = label.get_text().strip()
                    if any(k in label_text for k in ['Route', 'Distance', 'Estimate']):
                        parent = label.parent
                        elem = parent.find('p', class_='form-control-static') or parent.find('span')
                        if elem:
                            movement_data['route_estimate'] = elem.get_text().strip()
                            break
            
            if movement_data['route_estimate']:
                dist_match = re.search(r'([\d,\.]+)\s*km', movement_data['route_estimate'])
                if dist_match:
                    movement_data['route_distance_km'] = float(dist_match.group(1).replace(',', '.'))
                dur_match = re.search(r'(\d+h\s*\d*m?)', movement_data['route_estimate'])
                if dur_match:
                    movement_data['route_duration'] = dur_match.group(1).strip()
            
            # === UNIT NO ===
            unit_el = soup.find('input', {'id': 'UnitNo'}) or soup.find('input', {'name': 'UnitNo'})
            if unit_el:
                movement_data['unit_no'] = unit_el.get('value', '').strip()
            else:
                for label in soup.find_all('label'):
                    if 'Unit' in label.get_text():
                        elem = label.parent.find('p', class_='form-control-static')
                        if elem:
                            movement_data['unit_no'] = elem.get_text().strip()
                            break
            
            # === DATES ===
            coll_date_el = soup.find('input', {'id': 'CollectionDate'}) or soup.find('input', {'name': 'CollectionDate'})
            if coll_date_el:
                movement_data['collection_date'] = coll_date_el.get('value', '').strip()
            
            deliv_date_el = soup.find('input', {'id': 'DeliveryDate'}) or soup.find('input', {'name': 'DeliveryDate'})
            if deliv_date_el:
                movement_data['delivery_date'] = deliv_date_el.get('value', '').strip()
            
            # === COLLECTION ADDRESS ===
            collection_data = {'name': None, 'address': None, 'tel': None, 'email': None}
            collection_h2 = soup.find('h2', string='Collection Address')
            if collection_h2:
                parent_div = collection_h2.find_next()
                if parent_div:
                    h4_elements = parent_div.parent.find_all('h4', limit=2)
                    if len(h4_elements) >= 1:
                        name_text = h4_elements[0].get_text().strip()
                        match = re.search(r'\(([^)]+)\)', name_text)
                        code = match.group(1) if match else ''
                        collection_data['name'] = name_text.replace(f'({code})', '').strip() if code else name_text
                    if len(h4_elements) >= 2:
                        collection_data['address'] = h4_elements[1].get_text().strip()
                    
                    current = h4_elements[-1] if h4_elements else parent_div
                    for elem in current.find_all_next():
                        if elem.name in ['h2', 'h1']: break
                        text = elem.get_text().strip()
                        if text.startswith('Tel No.'):
                            tel_match = re.search(r'Tel No\.:\s*([\d\s/\-\+]+)', text)
                            if tel_match: collection_data['tel'] = tel_match.group(1).strip()
                        if text.startswith('Email'):
                            email_match = re.search(r'Email:\s*([^\s<]+)', text)
                            if email_match: collection_data['email'] = email_match.group(1).strip()
                        if collection_data['tel'] and collection_data['email']: break
            movement_data['collection_address_full'] = collection_data
            
            # === DELIVERY ADDRESS ===
            delivery_data = {'name': None, 'address': None, 'tel': None, 'email': None}
            delivery_h2 = soup.find('h2', string='Delivery Address')
            if delivery_h2:
                parent_div = delivery_h2.find_next()
                if parent_div:
                    h4_elements = parent_div.parent.find_all('h4', limit=2)
                    if len(h4_elements) >= 1:
                        name_text = h4_elements[0].get_text().strip()
                        match = re.search(r'\(([^)]+)\)', name_text)
                        code = match.group(1) if match else ''
                        delivery_data['name'] = name_text.replace(f'({code})', '').strip() if code else name_text
                    if len(h4_elements) >= 2:
                        delivery_data['address'] = h4_elements[1].get_text().strip()
                    
                    current = h4_elements[-1] if h4_elements else parent_div
                    for elem in current.find_all_next():
                        if elem.name in ['h2', 'h1']: break
                        text = elem.get_text().strip()
                        if text.startswith('Tel No.'):
                            tel_match = re.search(r'Tel No\.:\s*([\d\s/\-\+]+)', text)
                            if tel_match: delivery_data['tel'] = tel_match.group(1).strip()
                        if text.startswith('Email'):
                            email_match = re.search(r'Email:\s*([^\s<]+)', text)
                            if email_match: delivery_data['email'] = email_match.group(1).strip()
                        if delivery_data['tel'] and delivery_data['email']: break
            movement_data['delivery_address_full'] = delivery_data
            
            # === CHARGE ===
            charge_el = soup.find('input', {'id': 'DeliveryCharge'}) or soup.find('input', {'name': 'DeliveryCharge'})
            if charge_el:
                movement_data['delivery_charge'] = charge_el.get('value', '').strip()
            
            return movement_data
        else:
            return {'movement_id': movement_id, 'error': f'HTTP {response.status_code}'}
    except Exception as e:
        return {'movement_id': movement_id, 'error': str(e)}


def enrich_missions_with_details(session, missions, country="france", headers=None, delay=0.3):
    enriched = []
    total = len(missions)
    for idx, mission in enumerate(missions):
        percent = int((idx + 1) / total * 100)
        reg_no = mission.get('RegNo', 'N/A')
        print(f"[{percent}%] {idx+1}/{total} - {reg_no}")
        
        movement_id = mission.get('Id')
        if movement_id:
            debug = (idx == 0)
            details = get_mission_details(session, movement_id, country, headers, debug=debug)
            enriched_mission = {**mission, **details}
            if details.get('vin'): print(f"     VIN: {details['vin']}")
            if details.get('fuel_type'): print(f"     Fuel: {details['fuel_type']}")
            if details.get('route_estimate'): print(f"     Route: {details['route_estimate']}")
        else:
            enriched_mission = mission
        
        enriched.append(enriched_mission)
        if idx < total - 1: time.sleep(delay)
    
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
        return jsonify({'success': True, 'data': data, 'message': f"Scraping FRANCE: {data['total_outbound']} outbound, {data['total_inbound']} inbound"})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'country': 'FRANCE', 'timestamp': datetime.utcnow().isoformat()}), 500

@app.route('/scrape/germany')
def scrape_germany():
    try:
        data = scrape_erac_country("germany", enrich_details=True)
        return jsonify({'success': True, 'data': data, 'message': f"Scraping GERMANY: {data['total_outbound']} outbound, {data['total_inbound']} inbound"})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'country': 'GERMANY', 'timestamp': datetime.utcnow().isoformat()}), 500

@app.route('/debug/movement/<movement_id>')
def debug_movement(movement_id):
    try:
        login_id = os.getenv('ERAC_GERMANY_LOGIN')
        password = os.getenv('ERAC_GERMANY_PASSWORD')
        if not login_id or not password:
            return jsonify({'success': False, 'error': 'Env vars manquantes'}), 500
        
        headers = {'Accept': 'text/html,*/*;q=0.8', 'User-Agent': 'Mozilla/5.0'}
        session = requests.Session()
        
        login_page = session.get('https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound', headers=headers)
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
    
    login_page = session.get('https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound', headers=headers)
    soup = BeautifulSoup(login_page.text, 'html.parser')
    token_el = soup.find('input', {'name': '__RequestVerificationToken'})
    if not token_el:
        raise ValueError("Token non trouve")
    token = token_el['value']
    
    login_payload = {'LoginId': login_id, 'Password': password, '__RequestVerificationToken': token}
    login_headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    login_headers.update(headers)
    
    session.post('https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FOutbound', data=login_payload, headers=login_headers)
    session.post('https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FCollection%2FInbound', data=login_payload, headers=login_headers)
    
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
                service_options.append({'value': opt.get('value', ''), 'label': opt.get_text(strip=True), 'selected': opt.has_attr('selected')})
        
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
            return {'country': country.upper(), 'status': status, 'vehicles': [], 'count': 0, 'timestamp': datetime.utcnow().isoformat()}
        
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
        return jsonify({'success': False, 'error': str(e), 'country': 'GERMANY', 'timestamp': datetime.utcnow().isoformat()}), 500

@app.route('/scrape/france/tenders')
def scrape_france_tenders():
    try:
        data = scrape_intender("france")
        return jsonify({'success': True, 'data': data, 'message': f"InTender FRANCE: {data['count']} vehicules"})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'country': 'FRANCE', 'timestamp': datetime.utcnow().isoformat()}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5030))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    print(f"ERAC Scraper v3.1 sur port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
