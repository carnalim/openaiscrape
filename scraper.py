import requests
from bs4 import BeautifulSoup
import sqlite3
import json
import logging
import re
import time
import concurrent.futures

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect('models.db')
    c = conn.cursor()
    c.execute('''DROP TABLE IF EXISTS models''')
    c.execute('''
        CREATE TABLE models
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         name TEXT NOT NULL,
         slug TEXT NOT NULL,
         model_id TEXT,
         providers TEXT,
         provider_details TEXT,
         description TEXT,
         timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
    ''')
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

def clean_text(text):
    """Clean and normalize text content"""
    if not text:
        return None
    return re.sub(r'\s+', ' ', text.strip())

def get_model_details(model_path):
    """Get detailed information for a model"""
    models_url = "https://openrouter.ai/api/v1/models"
    headers = {
        'Authorization': 'Bearer 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',
        'HTTP-Referer': 'https://localhost:5000',
        'Accept': 'application/json',
        'User-Agent': 'OpenAIScraper/1.0.0'
    }
    
    try:
        # Get all models
        response = requests.get(models_url, headers=headers)
        response.raise_for_status()
        models_data = response.json()
        
        # Find the model in the API response
        model_data = None
        for model in models_data.get('data', []):
            if model.get('id') == model_path:
                model_data = model
                break
        
        # Extract provider from model path
        provider = model_path.split('/')[0]
        providers = [provider]
        
        # Use default values if model not found
        if not model_data:
            return {
                'providers': providers,
                'provider_details': {
                    provider: {
                        'context': '32K tokens',
                        'max_output': '4K tokens',
                        'input_price': '$0.0005/1K tokens',
                        'output_price': '$0.0005/1K tokens',
                        'url': f'https://{provider}.ai' if provider != 'openrouter' else 'https://openrouter.ai'
                    }
                },
                'description': f"Advanced language model from {provider.title()} with strong performance across various tasks."
            }
        
        # Format pricing information
        context_window = model_data.get('context_length', 32000)
        context_window_k = f"{context_window // 1000}K"
        input_price = model_data.get('pricing', {}).get('input', 0.0005)
        output_price = model_data.get('pricing', {}).get('output', 0.0005)
        
        # Create provider details
        provider_details = {
            provider: {
                'context': f"{context_window_k} tokens",
                'max_output': '4K tokens',
                'input_price': f"${input_price:.4f}/1K tokens",
                'output_price': f"${output_price:.4f}/1K tokens",
                'url': f'https://{provider}.ai' if provider != 'openrouter' else 'https://openrouter.ai'
            }
        }
        
        # Get description from API or generate one
        description = model_data.get('description')
        if not description:
            provider = model_path.split('/')[0].title()
            description = f"Advanced language model from {provider} with strong performance across various tasks."
        
        return {
            'providers': providers,
            'provider_details': provider_details,
            'description': description
        }
        
    except Exception as e:
        logger.error(f"Error getting model details from API: {str(e)}")
        # Fallback to default values on error
        provider = model_path.split('/')[0].lower()
        return {
            'providers': providers if 'providers' in locals() else ['openrouter'],
            'provider_details': {
                'openrouter': {
                    'context': '32K tokens',
                    'max_output': '4K tokens',
                    'input_price': '$0.0005/1K tokens',
                    'output_price': '$0.0005/1K tokens',
                    'url': 'https://openrouter.ai'
                }
            },
            'description': f"Advanced language model from {provider.title()} with strong performance across various tasks."
        }

def get_all_models():
    """Get all models from OpenRouter.ai API"""
    api_url = "https://openrouter.ai/api/v1/models"
    headers = {
        'Authorization': 'Bearer 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',
        'HTTP-Referer': 'https://localhost:5000',  # Required by OpenRouter
        'Accept': 'application/json'
    }
    
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # Get models from API
        models = []
        for model in data.get('data', []):
            model_id = model.get('id', '')
            if '/' in model_id:  # Only include models with provider/model format
                models.append(model_id)
        
        logger.info(f"Found {len(models)} models")
        return models
    except Exception as e:
        logger.error(f"Error getting models: {str(e)}")
        return []

def process_model(model_path):
    """Process a single model"""
    try:
        logger.info(f"Processing model: {model_path}")
        # Format model name, handling special cases
        name_part = model_path.split('/')[-1]
        if name_part == 'codestral-mamba':
            name = 'Codestral Mamba'
        else:
            name = name_part.replace('-', ' ').title()
        details = get_model_details(model_path)
        
        if details:
            return {
                "name": name,
                "slug": model_path.split('/')[-1],
                "model_id": model_path,
                "providers": details['providers'],
                "provider_details": details['provider_details'],
                "description": details['description']
            }
    except Exception as e:
        logger.error(f"Error processing model {model_path}: {str(e)}")
    return None

def scrape_models():
    """Scrape all models with concurrent processing"""
    model_paths = get_all_models()
    logger.info(f"Found {len(model_paths)} models")
    
    models = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_model = {executor.submit(process_model, path): path for path in model_paths}
        for future in concurrent.futures.as_completed(future_to_model):
            model = future.result()
            if model:
                models.append(model)
    
    try:
        # Store in database
        conn = sqlite3.connect('models.db')
        c = conn.cursor()
        
        # Clear existing entries
        c.execute('DELETE FROM models')
        
        # Insert new entries
        for model in models:
            c.execute('''
                INSERT INTO models 
                (name, slug, model_id, providers, provider_details, description)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                model['name'],
                model['slug'],
                model['model_id'],
                json.dumps(model['providers']),
                json.dumps(model['provider_details']),
                model['description']
            ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Successfully stored {len(models)} models in database")
        return models
    except Exception as e:
        logger.error(f"Error storing models in database: {str(e)}")
        return []

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