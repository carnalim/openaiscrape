import requests
import sqlite3
import json
import logging
import re
import time
import concurrent.futures
from playwright.sync_api import sync_playwright

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect('models.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS models
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         name TEXT NOT NULL,
         slug TEXT NOT NULL UNIQUE,
         model_id TEXT,
         providers TEXT,
         provider_details TEXT,
         description TEXT,
         timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
    ''')
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

def scrape_provider_details(model_path):
    """Scrape provider details using Playwright"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 720})
        page = context.new_page()
        
        try:
            url = f"https://openrouter.ai/{model_path}"
            logger.info(f"Scraping providers from {url}")
            
            page.goto(url)
            time.sleep(5)  # Wait for content to load
            
            providers = []
            provider_details = {}
            
            # Find provider rows in table
            rows = page.query_selector_all('tr')
            current_provider = None
            current_details = {}
            
            for row in rows:
                cells = row.query_selector_all('td')
                if cells and len(cells) > 1:
                    cell_texts = [cell.inner_text().strip() for cell in cells]
                    
                    # Check if this is a provider row - look for provider name in first cell
                    first_cell = cell_texts[0].lower()
                    if any(provider in first_cell for provider in ['anthropic', 'google', 'meta', 'mistral', 'openai']):
                        # Save previous provider details if exists
                        if current_provider and current_details:
                            providers.append(current_provider)
                            provider_details[current_provider] = current_details
                        
                        # Start new provider
                        current_provider = cell_texts[0]
                        current_details = {}
                        
                        # Set provider URL based on first word of provider name
                        provider_base = current_provider.lower().split()[0]
                        current_details['url'] = f'https://{provider_base}.ai'
                        
                        # If there's additional data in other cells, capture it
                        if len(cell_texts) > 1:
                            for i, text in enumerate(cell_texts[1:], 1):
                                if text.strip():  # Only add non-empty cells
                                    current_details[f'info_{i}'] = text.strip()
                    elif current_provider and len(cell_texts) >= 2:
                        # Add details to current provider
                        key = cell_texts[0].lower().strip()
                        value = cell_texts[1].strip()
                        
                        # Capture all relevant information
                        if key and value:  # Only store non-empty key-value pairs
                            if 'context' in key:
                                current_details['context'] = value
                            elif 'output' in key and '$' not in value:
                                current_details['max_output'] = value
                            elif 'input' in key and '$' in value:
                                current_details['input_price'] = value
                            elif 'output' in key and '$' in value:
                                current_details['output_price'] = value
                            elif 'latency' in key:
                                current_details['latency'] = value
                            elif 'throughput' in key:
                                current_details['throughput'] = value
                            else:
                                # Store any other relevant information
                                sanitized_key = key.replace(' ', '_').replace('/', '_')
                                current_details[sanitized_key] = value
            
            # Add last provider
            if current_provider and current_details:
                providers.append(current_provider)
                provider_details[current_provider] = current_details
            
            return {
                'providers': providers,
                'provider_details': provider_details
            }
            
        except Exception as e:
            logger.error(f"Error scraping provider details: {str(e)}")
            return None
        finally:
            browser.close()

def get_model_details(model_path, models_data):
    """Get detailed information for a model from OpenRouter"""
    # First try scraping the provider details
    scraped_details = scrape_provider_details(model_path)
    if scraped_details and scraped_details['providers']:
        # Get description from API
        description = None
        try:
            api_url = f"https://openrouter.ai/api/v1/models/{model_path}"
            headers = {
                'Authorization': 'Bearer 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',
                'HTTP-Referer': 'https://localhost:5000',
                'Accept': 'application/json'
            }
            response = requests.get(api_url, headers=headers)
            if response.ok:
                model_data = response.json()
                description = model_data.get('description')
        except:
            pass
        
        if not description:
            provider = model_path.split('/')[0].title()
            description = f"Advanced language model from {provider} with strong performance across various tasks."
        
        return {
            'providers': scraped_details['providers'],
            'provider_details': scraped_details['provider_details'],
            'description': description
        }
    
    # If scraping fails, fall back to API and defaults
    try:
        api_url = f"https://openrouter.ai/api/v1/models/{model_path}"
        headers = {
            'Authorization': 'Bearer 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',
            'HTTP-Referer': 'https://localhost:5000',
            'Accept': 'application/json'
        }
        
        try:
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()
            model_data = response.json()
            
            main_provider = model_path.split('/')[0]
            providers = [main_provider]
            
            context = model_data.get('context_length', 32000)
            max_output = model_data.get('max_output_tokens', 4000)
            input_price = model_data.get('pricing', {}).get('input', 0)
            output_price = model_data.get('pricing', {}).get('output', 0)
            latency = model_data.get('latency', 0)
            throughput = model_data.get('throughput', 0)
            
            provider_details = {
                main_provider: {
                    'context': f"{context // 1000}K tokens",
                    'max_output': f"{max_output // 1000}K tokens",
                    'input_price': f"${input_price:.2f}/1K tokens",
                    'output_price': f"${output_price:.2f}/1K tokens",
                    'latency': f"{latency:.2f}s",
                    'throughput': f"{throughput:.2f}t/s",
                    'url': f'https://{main_provider}.ai' if main_provider != 'openrouter' else 'https://openrouter.ai'
                }
            }
            
            description = model_data.get('description')
            if not description:
                description = f"Advanced language model from {main_provider.title()} with strong performance across various tasks."
            
            return {
                'providers': providers,
                'provider_details': provider_details,
                'description': description
            }
        except:
            main_provider = model_path.split('/')[0]
            return {
                'providers': [main_provider],
                'provider_details': {
                    main_provider: {
                        'context': '32K tokens',
                        'max_output': '4K tokens',
                        'input_price': '$0.00/1K tokens',
                        'output_price': '$0.00/1K tokens',
                        'latency': 'N/A',
                        'throughput': 'N/A',
                        'url': f'https://{main_provider}.ai' if main_provider != 'openrouter' else 'https://openrouter.ai'
                    }
                },
                'description': f"Advanced language model from {main_provider.title()} with strong performance across various tasks."
            }
            
    except Exception as e:
        logger.error(f"Error getting model details: {str(e)}")
        main_provider = model_path.split('/')[0]
        return {
            'providers': [main_provider],
            'provider_details': {
                main_provider: {
                    'context': '32K tokens',
                    'max_output': '4K tokens',
                    'input_price': '$0.00/1K tokens',
                    'output_price': '$0.00/1K tokens',
                    'latency': 'N/A',
                    'throughput': 'N/A',
                    'url': f'https://{main_provider}.ai' if main_provider != 'openrouter' else 'https://openrouter.ai'
                }
            },
            'description': f"Advanced language model from {main_provider.title()} with strong performance across various tasks."
        }

def get_all_models():
    """Get all models from OpenRouter.ai API"""
    api_url = "https://openrouter.ai/api/v1/models"
    headers = {
        'Authorization': 'Bearer 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',
        'HTTP-Referer': 'https://localhost:5000',
        'Accept': 'application/json'
    }
    
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        models = []
        for model in data.get('data', []):
            model_id = model.get('id', '')
            if '/' in model_id:  # Only include models with provider/model format
                models.append(model_id)
        
        logger.info(f"Found {len(models)} models")
        return models, data
    except Exception as e:
        logger.error(f"Error getting models: {str(e)}")
        return [], None

def process_model(model_path, models_data):
    """Process a single model"""
    try:
        logger.info(f"Processing model: {model_path}")
        name_part = model_path.split('/')[-1]
        if name_part == 'codestral-mamba':
            name = 'Codestral Mamba'
        else:
            name = name_part.replace('-', ' ').title()
        details = get_model_details(model_path, models_data)
        
        if details:
            model_data = {
                "name": name,
                "slug": model_path.split('/')[-1],
                "model_id": model_path,
                "providers": details['providers'],
                "provider_details": details['provider_details'],
                "description": details['description']
            }
            
            # Store model in database immediately
            conn = sqlite3.connect('models.db')
            c = conn.cursor()
            
            try:
                c.execute('''
                    INSERT OR REPLACE INTO models 
                    (name, slug, model_id, providers, provider_details, description)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    model_data['name'],
                    model_data['slug'],
                    model_data['model_id'],
                    json.dumps(model_data['providers']),
                    json.dumps(model_data['provider_details']),
                    model_data['description']
                ))
                conn.commit()
            except Exception as e:
                logger.error(f"Error storing model in database: {str(e)}")
            finally:
                conn.close()
            
            return model_data
    except Exception as e:
        logger.error(f"Error processing model {model_path}: {str(e)}")
    return None

def scrape_models(should_stop=None):
    """Scrape all models with concurrent processing"""
    model_paths, models_data = get_all_models()
    if not models_data:
        return []
        
    logger.info(f"Found {len(model_paths)} models")
    
    models = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_model = {executor.submit(process_model, path, models_data): path for path in model_paths}
        for future in concurrent.futures.as_completed(future_to_model):
            if should_stop and should_stop():
                logger.info("Stopping model scraping as requested")
                executor.shutdown(wait=False)
                break
                
            model = future.result()
            if model:
                models.append(model)
    
    if not (should_stop and should_stop()):
        logger.info(f"Successfully stored {len(models)} models in database")
    return models

def get_models():
    try:
        conn = sqlite3.connect('models.db')
        c = conn.cursor()
        c.execute('''
            SELECT name, slug, model_id, providers, provider_details, description 
            FROM models ORDER BY name
        ''')
        models = [{
            'name': row[0],
            'slug': row[1],
            'model_id': row[2],
            'providers': json.loads(row[3]),
            'provider_details': json.loads(row[4]),
            'description': row[5]
        } for row in c.fetchall()]
        conn.close()
        return models
    except Exception as e:
        logger.error(f"Error getting models from database: {str(e)}")
        return []

def get_model_by_slug(slug):
    try:
        conn = sqlite3.connect('models.db')
        c = conn.cursor()
        c.execute('''
            SELECT name, slug, model_id, providers, provider_details, description 
            FROM models WHERE slug = ?
        ''', (slug,))
        row = c.fetchone()
        conn.close()
        if row:
            return {
                'name': row[0],
                'slug': row[1],
                'model_id': row[2],
                'providers': json.loads(row[3]),
                'provider_details': json.loads(row[4]),
                'description': row[5]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting model by slug: {str(e)}")
        return None

if __name__ == '__main__':
    init_db()
    scrape_models()