# tender_scraper.py - Module de scraping InTender pour ERAC
# À intégrer dans main.py existant
# Scrape les offres ouvertes au bidding sur Enterprise Mobility

from flask import Flask, jsonify, request
from bs4 import BeautifulSoup
import requests
import os
import re
from datetime import datetime

# ============================================================
# FONCTIONS DE SCRAPING INTENDER
# ============================================================

def parse_tender_vehicles(html_content):
    """
    Parse le HTML de la page InTender pour extraire tous les véhicules.
    La page InTender est du HTML statique (pas AJAX), les données sont
    directement dans le DOM sous forme de <tr> dans #tblVehicles.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    vehicles = []
    
    # === METADATA DU TENDER ===
    tender_meta = {
        'end_date': None,
        'end_date_ticks': None,
        'server_time': None,
        'currency': None,
        'is_active': None,
        'on_hold': None
    }
    
    # Récupérer les hidden inputs de metadata
    end_date_el = soup.find('input', {'id': 'EndDate'})
    if end_date_el:
        tender_meta['end_date'] = end_date_el.get('value', '').strip()
    
    end_date_ticks_el = soup.find('input', {'id': 'EndDateTicks'})
    if end_date_ticks_el:
        tender_meta['end_date_ticks'] = end_date_ticks_el.get('value', '').strip()
    
    server_ticks_el = soup.find('input', {'id': 'ServerTicks'})
    if server_ticks_el:
        tender_meta['server_time'] = server_ticks_el.get('value', '').strip()
    
    currency_el = soup.find('input', {'id': 'Currency'})
    if currency_el:
        tender_meta['currency'] = currency_el.get('value', '').strip()
    
    is_active_el = soup.find('input', {'id': 'IsActive'})
    if is_active_el:
        tender_meta['is_active'] = is_active_el.get('value', '').strip()
    
    on_hold_el = soup.find('input', {'id': 'OnHold'})
    if on_hold_el:
        tender_meta['on_hold'] = on_hold_el.get('value', '').strip()
    
    # === PARSE CHAQUE VÉHICULE ===
    table = soup.find('table', {'id': 'tblVehicles'})
    if not table:
        print("⚠️ Table #tblVehicles non trouvée")
        return {'meta': tender_meta, 'vehicles': [], 'count': 0}
    
    rows = table.find('tbody').find_all('tr') if table.find('tbody') else []
    print(f"📋 {len(rows)} véhicules trouvés dans le tender")
    
    for idx, row in enumerate(rows):
        vehicle = parse_tender_row(row, idx)
        if vehicle:
            vehicles.append(vehicle)
    
    return {
        'meta': tender_meta,
        'vehicles': vehicles,
        'count': len(vehicles)
    }


def parse_tender_row(row, idx):
    """
    Parse une ligne <tr> du tableau InTender.
    Structure des colonnes:
    0: Link Move (input)
    1: Make Model (text)
    2: Vehicle Type (text)
    3: Collection code (text)
    4: Collection Town (text)
    5: Collection Post Code (text)
    6: Delivery code (text)
    7: Delivery Town (text)
    8: Delivery Post Code (text)
    9: Del Date (input)
    10: Charge (input)
    11: Service (select)
    12: Route Estimate (text)
    13: Desired Collect Date (text)
    14: Desired Delivery Date (text)
    15: Special Instructions (text)
    """
    try:
        cells = row.find_all('td')
        if len(cells) < 12:
            print(f"  ⚠️ Row {idx}: pas assez de colonnes ({len(cells)})")
            return None
        
        # === TENDER VEHICLE ID (hidden input avant les <td>) ===
        tender_vehicle_id_el = row.find('input', {'name': re.compile(r'Vehicles\[\d+\]\.TenderVehicleId')})
        tender_vehicle_id = tender_vehicle_id_el.get('value', '') if tender_vehicle_id_el else None
        
        # === LINK MOVE ===
        link_move_el = cells[0].find('input')
        link_move = link_move_el.get('value', '').strip() if link_move_el else ''
        
        # === MAKE MODEL ===
        # Le texte est dans le <td> avec des <br/> entre marque et modèle
        make_model_raw = cells[1].get_text(separator=' ', strip=True)
        # Nettoyer les espaces multiples
        make_model = re.sub(r'\s+', ' ', make_model_raw).strip()
        
        # Séparer marque et modèle si possible
        make_model_parts = cells[1].decode_contents().split('<br')
        make = make_model_parts[0].strip() if len(make_model_parts) > 0 else make_model
        model = ''
        if len(make_model_parts) > 1:
            # Nettoyer le tag <br/> ou <br />
            model_raw = make_model_parts[1]
            model = re.sub(r'^[/\s>]+', '', model_raw).strip()
            # Supprimer les tags HTML restants
            model = BeautifulSoup(model, 'html.parser').get_text().strip()
        
        # === VEHICLE TYPE + FUEL ===
        vehicle_type_raw = cells[2].get_text(separator='|', strip=True)
        vehicle_type_parts = vehicle_type_raw.split('|')
        vehicle_type = vehicle_type_parts[0].strip() if len(vehicle_type_parts) > 0 else ''
        fuel_type = vehicle_type_parts[1].strip() if len(vehicle_type_parts) > 1 else ''
        
        # === COLLECTION ===
        collection_code = cells[3].get_text(strip=True)
        collection_town = cells[4].get_text(strip=True)
        collection_post_code = cells[5].get_text(strip=True)
        
        # === DELIVERY ===
        delivery_code = cells[6].get_text(strip=True)
        delivery_town = cells[7].get_text(strip=True)
        delivery_post_code = cells[8].get_text(strip=True)
        
        # === DELIVERY DATE (input éditable - valeur existante si déjà biddé) ===
        del_date_el = cells[9].find('input')
        existing_delivery_date = del_date_el.get('value', '').strip() if del_date_el else ''
        
        # === CHARGE (input éditable - valeur existante si déjà biddé) ===
        charge_el = cells[10].find('input')
        existing_charge = charge_el.get('value', '').strip() if charge_el else ''
        
        # === SERVICE TYPE (select) ===
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
        
        # === ROUTE ESTIMATE ===
        route_estimate = cells[12].get_text(strip=True) if len(cells) > 12 else ''
        
        # Parse distance et durée si disponible (format: "93,4km\n1h 13m")
        route_distance_km = None
        route_duration = None
        if route_estimate:
            dist_match = re.search(r'([\d,\.]+)\s*km', route_estimate)
            if dist_match:
                route_distance_km = float(dist_match.group(1).replace(',', '.'))
            dur_match = re.search(r'(\d+h\s*\d*m?)', route_estimate)
            if dur_match:
                route_duration = dur_match.group(1).strip()
        
        # === DESIRED COLLECT DATE ===
        desired_collect_date = ''
        if len(cells) > 13:
            desired_collect_date = cells[13].get_text(strip=True)
        
        # === DESIRED DELIVERY DATE ===
        desired_delivery_date = ''
        if len(cells) > 14:
            desired_delivery_date = cells[14].get_text(strip=True)
        
        # === SPECIAL INSTRUCTIONS ===
        special_instructions = ''
        if len(cells) > 15:
            special_instructions = cells[15].get_text(strip=True)
        
        # Parse special instructions pour flags utiles
        needs_trailer = bool(re.search(r'needs?\s+trailer', special_instructions, re.IGNORECASE))
        is_driveable = bool(re.search(r'driveable', special_instructions, re.IGNORECASE))
        is_rollable = bool(re.search(r'rollable', special_instructions, re.IGNORECASE))
        
        # Extraire le group code entre parenthèses (ex: "G3UI", "G3J1")
        group_ref_match = re.search(r'\(([A-Z0-9]+)\)\s*$', special_instructions)
        group_ref = group_ref_match.group(1) if group_ref_match else ''
        
        vehicle = {
            # Identifiants
            'tender_vehicle_id': tender_vehicle_id,
            'vehicle_index': idx,
            
            # Véhicule
            'make_model': make_model,
            'make': make,
            'model': model,
            'vehicle_type': vehicle_type,  # CAR, COM
            'fuel_type': fuel_type,        # Diesel, bleifrei, etc.
            
            # Collection (départ)
            'collection_code': collection_code,
            'collection_town': collection_town,
            'collection_post_code': collection_post_code,
            
            # Delivery (arrivée)
            'delivery_code': delivery_code,
            'delivery_town': delivery_town,
            'delivery_post_code': delivery_post_code,
            
            # Route
            'route_estimate_raw': route_estimate,
            'route_distance_km': route_distance_km,
            'route_duration': route_duration,
            
            # Dates
            'desired_collect_date': desired_collect_date,
            'desired_delivery_date': desired_delivery_date,
            
            # Bid existant (si déjà rempli)
            'existing_charge': existing_charge,
            'existing_delivery_date': existing_delivery_date,
            
            # Service
            'service_type': service_type,
            'service_options': service_options,
            
            # Instructions spéciales
            'special_instructions': special_instructions,
            'needs_trailer': needs_trailer,
            'is_driveable': is_driveable,
            'is_rollable': is_rollable,
            'group_ref': group_ref,
            
            # Link Move
            'link_move': link_move
        }
        
        print(f"  ✓ [{idx}] {make_model} | {collection_town} → {delivery_town} | {route_distance_km}km")
        return vehicle
        
    except Exception as e:
        print(f"  ❌ Erreur parsing row {idx}: {str(e)}")
        return None


def scrape_intender(country="germany"):
    """
    Scrape la page InTender pour récupérer toutes les offres ouvertes au bidding.
    Utilise la même authentification que le scraper existant.
    """
    try:
        print(f"🎯 Début du scraping InTender {country.upper()}...")
        
        # Credentials
        if country.lower() == "germany":
            login_id = os.getenv('ERAC_GERMANY_LOGIN')
            password = os.getenv('ERAC_GERMANY_PASSWORD')
        else:
            login_id = os.getenv('ERAC_FRANCE_LOGIN')
            password = os.getenv('ERAC_FRANCE_PASSWORD')
        
        if not login_id or not password:
            raise ValueError(f"⚠️ Variables d'env manquantes pour {country.upper()}")
        
        session = requests.Session()
        
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        }
        
        # === ÉTAPE 1: Login ===
        print("🔐 Connexion...")
        login_page = session.get(
            'https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FTender%2FInTender',
            headers=headers
        )
        
        login_soup = BeautifulSoup(login_page.text, 'html.parser')
        token_el = login_soup.find('input', {'name': '__RequestVerificationToken'})
        
        if not token_el:
            raise ValueError("Token de vérification non trouvé")
        
        token = token_el['value']
        
        login_payload = {
            'LoginId': login_id,
            'Password': password,
            '__RequestVerificationToken': token,
        }
        
        login_headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        login_headers.update(headers)
        
        login_response = session.post(
            'https://erac.hkremarketing.com/Login?ReturnUrl=%2FVendor%2FTender%2FInTender',
            data=login_payload,
            headers=login_headers
        )
        print(f"✓ Login response: {login_response.status_code}")
        
        # === ÉTAPE 2: Accepter les conditions (si nécessaire) ===
        print("⚖️ Vérification des conditions...")
        terms_page = session.get('https://erac.hkremarketing.com/vendor/scoc', headers=headers)
        terms_soup = BeautifulSoup(terms_page.text, 'html.parser')
        
        terms_token = terms_soup.find('input', {'name': '__RequestVerificationToken'})
        if terms_token:
            accept_payload = {
                'action': 'agree',
                '__RequestVerificationToken': terms_token['value'],
            }
            accept_headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            accept_headers.update(headers)
            session.post(
                'https://erac.hkremarketing.com/vendor/scoc',
                data=accept_payload,
                headers=accept_headers
            )
            print("✓ Conditions acceptées")
        
        # === ÉTAPE 3: Récupérer la page InTender ===
        print("📊 Récupération de la page InTender...")
        tender_response = session.get(
            'https://erac.hkremarketing.com/Vendor/Tender/InTender',
            headers=headers
        )
        
        if tender_response.status_code != 200:
            raise ValueError(f"HTTP {tender_response.status_code} sur InTender")
        
        # Vérifier qu'on est bien sur la bonne page
        if 'Offered for Tender' not in tender_response.text:
            # On est peut-être redirigé vers le login
            if 'Login' in tender_response.text:
                raise ValueError("Session expirée - redirigé vers login")
            # Ou pas de tender actif
            if 'Closed' in tender_response.text or 'No vehicles' in tender_response.text:
                return {
                    'country': country.upper(),
                    'status': 'no_active_tender',
                    'vehicles': [],
                    'count': 0,
                    'timestamp': datetime.utcnow().isoformat()
                }
        
        print("✓ Page InTender récupérée")
        
        # === ÉTAPE 4: Parser le HTML ===
        print("🔍 Parsing des véhicules...")
        result = parse_tender_vehicles(tender_response.text)
        
        # Ajouter les métadonnées
        result['country'] = country.upper()
        result['status'] = 'active'
        result['timestamp'] = datetime.utcnow().isoformat()
        result['source_url'] = 'https://erac.hkremarketing.com/Vendor/Tender/InTender'
        
        print(f"✅ Scraping InTender terminé: {result['count']} véhicules")
        
        return result
        
    except Exception as e:
        print(f"❌ Erreur scraping InTender: {str(e)}")
        raise


# ============================================================
# ENDPOINTS FLASK À AJOUTER À main.py
# ============================================================

def register_tender_routes(app):
    """
    Enregistre les routes InTender dans l'app Flask existante.
    Usage dans main.py: 
        from tender_scraper import register_tender_routes
        register_tender_routes(app)
    """
    
    @app.route('/scrape/germany/tenders')
    def scrape_germany_tenders():
        """Scrape les offres ouvertes au bidding pour l'Allemagne"""
        try:
            data = scrape_intender("germany")
            return jsonify({
                'success': True,
                'data': data,
                'message': f"✅ InTender GERMANY: {data['count']} véhicules à bidder"
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e),
                'country': 'GERMANY',
                'timestamp': datetime.utcnow().isoformat()
            }), 500
    
    @app.route('/scrape/france/tenders')
    def scrape_france_tenders():
        """Scrape les offres ouvertes au bidding pour la France"""
        try:
            data = scrape_intender("france")
            return jsonify({
                'success': True,
                'data': data,
                'message': f"✅ InTender FRANCE: {data['count']} véhicules à bidder"
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e),
                'country': 'FRANCE',
                'timestamp': datetime.utcnow().isoformat()
            }), 500


# ============================================================
# TEST LOCAL
# ============================================================

if __name__ == '__main__':
    # Test standalone
    app = Flask(__name__)
    register_tender_routes(app)
    
    print("🧪 Test du scraper InTender...")
    print("Endpoints:")
    print("  GET /scrape/germany/tenders")
    print("  GET /scrape/france/tenders")
    
    app.run(host='0.0.0.0', port=5031, debug=True)
