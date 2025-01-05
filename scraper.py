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
    provider = model_path.split('/')[0].lower()
    
    # Default provider stats
    default_stats = {
        'context': '32K tokens',
        'max_output': '4K tokens',
        'input_price': '$0.0005/1K tokens',
        'output_price': '$0.0005/1K tokens',
        'url': 'https://openrouter.ai/docs'
    }
    
    # Provider-specific configurations
    provider_configs = {
        'deepseek': {
            'providers': ['openrouter'],
            'stats': {
                'openrouter': {
                    'context': '64K tokens',
                    'max_output': '4K tokens',
                    'input_price': '$0.14/1K tokens',
                    'output_price': '$0.28/1K tokens',
                    'url': 'https://openrouter.ai'
                }
            }
        },
        'anthropic': {
            'providers': ['anthropic', 'openrouter'],
            'stats': {
                'anthropic': {
                    'context': '100K tokens',
                    'max_output': '4K tokens',
                    'input_price': '$0.008/1K tokens',
                    'output_price': '$0.024/1K tokens',
                    'url': 'https://www.anthropic.com'
                },
                'openrouter': {
                    'context': '100K tokens',
                    'max_output': '4K tokens',
                    'input_price': '$0.008/1K tokens',
                    'output_price': '$0.024/1K tokens',
                    'url': 'https://openrouter.ai'
                }
            }
        },
        'anthropic/claude-3.5-haiku-20241022': {
            'providers': ['anthropic', 'openrouter'],
            'stats': {
                'anthropic': {
                    'context': '200K tokens',
                    'max_output': '4K tokens',
                    'input_price': '$0.8/1K tokens',
                    'output_price': '$4/1K tokens',
                    'url': 'https://www.anthropic.com'
                },
                'openrouter': {
                    'context': '200K tokens',
                    'max_output': '4K tokens',
                    'input_price': '$0.8/1K tokens',
                    'output_price': '$4/1K tokens',
                    'url': 'https://openrouter.ai'
                }
            }
        },
        'openai': {
            'providers': ['openai'],
            'stats': {
                'openai': {
                    'context': '128K tokens',
                    'max_output': '4K tokens',
                    'input_price': '$0.01/1K tokens',
                    'output_price': '$0.03/1K tokens',
                    'url': 'https://openai.com'
                }
            }
        },
        'mistralai': {
            'providers': ['mistralai', 'openrouter'],
            'stats': {
                'mistralai': {
                    'context': '32K tokens',
                    'max_output': '4K tokens',
                    'input_price': '$0.0002/1K tokens',
                    'output_price': '$0.0002/1K tokens',
                    'url': 'https://mistral.ai'
                },
                'openrouter': {
                    'context': '32K tokens',
                    'max_output': '4K tokens',
                    'input_price': '$0.0002/1K tokens',
                    'output_price': '$0.0002/1K tokens',
                    'url': 'https://openrouter.ai/models'
                }
            }
        },
        'inflatebot': {
            'providers': ['inflatebot', 'openrouter', 'together', 'fireworks'],
            'stats': {
                'inflatebot': {**default_stats, 'url': 'https://openrouter.ai/docs'},
                'openrouter': {**default_stats, 'url': 'https://openrouter.ai', 'input_price': '$0.0006/1K tokens', 'output_price': '$0.0006/1K tokens'},
                'together': {**default_stats, 'url': 'https://www.together.ai', 'input_price': '$0.0007/1K tokens', 'output_price': '$0.0007/1K tokens'},
                'fireworks': {**default_stats, 'url': 'https://fireworks.ai', 'input_price': '$0.0006/1K tokens', 'output_price': '$0.0006/1K tokens'}
            }
        },
        'meta-llama': {
            'providers': ['meta-llama', 'together', 'fireworks', 'openrouter'],
            'stats': {
                'meta-llama': {**default_stats, 'url': 'https://ai.meta.com'},
                'together': {**default_stats, 'url': 'https://www.together.ai', 'input_price': '$0.0007/1K tokens', 'output_price': '$0.0007/1K tokens'},
                'fireworks': {**default_stats, 'url': 'https://fireworks.ai', 'input_price': '$0.0006/1K tokens', 'output_price': '$0.0006/1K tokens'},
                'openrouter': {**default_stats, 'url': 'https://openrouter.ai', 'input_price': '$0.0006/1K tokens', 'output_price': '$0.0006/1K tokens'}
            }
        }
    }
    
    # Get provider configurations from both lookups
    path_config = provider_configs.get(model_path)
    provider_config = provider_configs.get(provider)
    
    # Special handling for Claude models
    if 'claude' in model_path.lower():
        provider_info = {
            'providers': ['anthropic', 'openrouter'],
            'stats': {
                'anthropic': {
                    'context': '200K tokens',
                    'max_output': '4K tokens',
                    'input_price': '$0.8/1K tokens',
                    'output_price': '$4/1K tokens',
                    'url': 'https://www.anthropic.com'
                },
                'openrouter': {
                    'context': '200K tokens',
                    'max_output': '4K tokens',
                    'input_price': '$0.8/1K tokens',
                    'output_price': '$4/1K tokens',
                    'url': 'https://openrouter.ai'
                }
            }
        }
    else:
        if path_config and provider_config:
            # Merge providers and stats from both configs
            merged_providers = list(set(path_config['providers'] + provider_config['providers']))
            merged_stats = {**provider_config['stats'], **path_config['stats']}
            provider_info = {
                'providers': merged_providers,
                'stats': merged_stats
            }
        elif path_config:
            provider_info = path_config
        elif provider_config:
            provider_info = provider_config
        else:
            # For unknown providers, check if they might be available through OpenRouter
            provider_info = {
                'providers': ['openrouter'],
                'stats': {
                    'openrouter': {**default_stats, 'url': 'https://openrouter.ai', 'input_price': '$0.0006/1K tokens', 'output_price': '$0.0006/1K tokens'}
                }
            }
    
    # Generate description based on model name
    model_name = model_path.split('/')[-1].replace('-', ' ').title()
    description = f"Advanced language model from {provider.title()} with strong performance across various tasks."
    
    return {
        'providers': provider_info['providers'],
        'provider_details': provider_info['stats'],
        'description': description
    }

def get_all_models():
    """Get all models from OpenRouter.ai API"""
    api_url = "https://openrouter.ai/api/v1/models"
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
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
        
        # Also get models from web scraping to ensure complete coverage
        logger.info("Getting additional models from web scraping")
        # Check multiple pages for models
        urls = [
            "https://openrouter.ai/docs",
            "https://openrouter.ai/models",
            "https://openrouter.ai/docs/models"
        ]
        
        for url in urls:
            web_response = requests.get(url, headers={'User-Agent': headers['User-Agent']})
            web_response.raise_for_status()
            soup = BeautifulSoup(web_response.text, 'html.parser')
            
            # Find all model links in the documentation
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                # Check for both docs/models and direct model paths
                model_match = re.search(r'(?:/docs/models/|/)([^/]+/[^/]+)(?:/|$)', href)
                if model_match:
                    model_path = model_match.group(1)
                    # Filter out non-model paths and ensure it's a valid model ID format
                    if ('/' in model_path and
                        not any(x in model_path.lower() for x in [
                            'docs/', '.com', '.gg', '.ai', 'quick-start', 'principles',
                            'models', 'routing', 'oauth', 'api', 'requests', 'responses',
                            'parameters', 'outputs', 'caching', 'transforms', 'errors',
                            'limits', 'integrations', 'frameworks', 'uptime', 'undefined'
                        ]) and
                        model_path not in models):
                        models.append(model_path)
            
            # Add specific models that might be missing
            specific_models = [
                "deepseek/deepseek-chat-v3-3",
                "deepseek/deepseek-chat-v2.5",
                "mistralai/codestral-mamba-v1.0",
                "anthropic/claude-3.5-haiku-20241022"
            ]
            
            # Add OpenRouter provider for all Claude models
            for model in models:
                if 'claude' in model.lower() and model not in specific_models:
                    specific_models.append(model)
            for model in specific_models:
                if model not in models:
                    models.append(model)
        
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