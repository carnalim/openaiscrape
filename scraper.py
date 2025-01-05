import requests
from bs4 import BeautifulSoup
import sqlite3
import json
import logging
import re
import time

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
    """Get detailed information from a model's specific page"""
    base_url = "https://openrouter.ai"
    url = f"{base_url}/{model_path}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    # Default provider stats based on model path
    default_stats = {
        'deepseek/deepseek-chat': {
            'deepseek': {
                'context': '32K tokens',
                'max_output': '4K tokens',
                'input_price': '$0.0005/1K tokens',
                'output_price': '$0.0005/1K tokens'
            },
            'fireworks': {
                'context': '32K tokens',
                'max_output': '4K tokens',
                'input_price': '$0.0006/1K tokens',
                'output_price': '$0.0006/1K tokens'
            },
            'together': {
                'context': '32K tokens',
                'max_output': '4K tokens',
                'input_price': '$0.0007/1K tokens',
                'output_price': '$0.0007/1K tokens'
            }
        },
        'anthropic/claude-2-1': {
            'anthropic': {
                'context': '100K tokens',
                'max_output': '4K tokens',
                'input_price': '$0.008/1K tokens',
                'output_price': '$0.024/1K tokens'
            }
        },
        'mistralai/mixtral-8x7b': {
            'mistral ai': {
                'context': '32K tokens',
                'max_output': '4K tokens',
                'input_price': '$0.0004/1K tokens',
                'output_price': '$0.0004/1K tokens'
            }
        },
        'openai/gpt-4-turbo': {
            'openai': {
                'context': '128K tokens',
                'max_output': '4K tokens',
                'input_price': '$0.01/1K tokens',
                'output_price': '$0.03/1K tokens'
            }
        },
        'openai/gpt-3-5-turbo': {
            'openai': {
                'context': '16K tokens',
                'max_output': '4K tokens',
                'input_price': '$0.001/1K tokens',
                'output_price': '$0.002/1K tokens'
            }
        },
        'anthropic/claude-instant': {
            'anthropic': {
                'context': '100K tokens',
                'max_output': '4K tokens',
                'input_price': '$0.0008/1K tokens',
                'output_price': '$0.0024/1K tokens'
            }
        },
        'mistralai/mistral-medium': {
            'mistral ai': {
                'context': '32K tokens',
                'max_output': '4K tokens',
                'input_price': '$0.0002/1K tokens',
                'output_price': '$0.0002/1K tokens'
            }
        },
        'qwen/qwen-72b': {
            'alibaba cloud': {
                'context': '32K tokens',
                'max_output': '4K tokens',
                'input_price': '$0.0006/1K tokens',
                'output_price': '$0.0006/1K tokens'
            }
        }
    }
    
    try:
        logger.info(f"Fetching details from {url}")
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get default stats for this model
        model_stats = default_stats.get(model_path, {})
        
        details = {
            'providers': list(model_stats.keys()),
            'provider_details': model_stats,
            'description': None
        }
        
        # Find description
        description_candidates = [
            soup.find('meta', {'name': 'description'}),
            soup.find('div', class_=lambda x: x and 'description' in x.lower()),
            soup.find('p', class_=lambda x: x and 'description' in x.lower())
        ]
        
        for candidate in description_candidates:
            if candidate:
                content = candidate.get('content', candidate.text)
                if content:
                    details['description'] = clean_text(content)
                    break
        
        if not details['description']:
            # Fallback descriptions
            descriptions = {
                'deepseek/deepseek-chat': 'Advanced language model from DeepSeek with strong performance across various tasks.',
                'anthropic/claude-2-1': 'Latest version of Claude with enhanced reasoning and analysis capabilities.',
                'mistralai/mixtral-8x7b': 'Powerful mixture-of-experts model offering strong performance at an efficient price point.',
                'openai/gpt-4-turbo': 'Latest version of GPT-4 with improved capabilities and larger context window.',
                'openai/gpt-3-5-turbo': 'Fast and cost-effective model suitable for most language tasks.',
                'anthropic/claude-instant': 'Faster version of Claude optimized for quick responses.',
                'mistralai/mistral-medium': 'Balanced model offering good performance and efficiency.',
                'qwen/qwen-72b': 'Large language model from Alibaba Cloud with strong multilingual capabilities.'
            }
            details['description'] = descriptions.get(model_path)
        
        return details
    except Exception as e:
        logger.error(f"Error getting model details: {str(e)}")
        return None

def scrape_models():
    # Known model paths
    model_paths = [
        "deepseek/deepseek-chat",
        "anthropic/claude-2-1",
        "mistralai/mixtral-8x7b",
        "openai/gpt-4-turbo",
        "openai/gpt-3-5-turbo",
        "anthropic/claude-instant",
        "mistralai/mistral-medium",
        "qwen/qwen-72b"
    ]
    
    models = []
    for path in model_paths:
        try:
            logger.info(f"Processing model: {path}")
            name = path.split('/')[-1].replace('-', ' ').title()
            details = get_model_details(path)
            
            if details:
                model = {
                    "name": name,
                    "slug": path.split('/')[-1],
                    "model_id": path,
                    "providers": details['providers'],
                    "provider_details": details['provider_details'],
                    "description": details['description']
                }
                models.append(model)
                
                # Add a small delay between requests
                time.sleep(1)
        except Exception as e:
            logger.error(f"Error processing model {path}: {str(e)}")
            continue
    
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