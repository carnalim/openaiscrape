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
    # Define headers for requests
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    # Known provider names to help with validation
    known_providers = {
        'deepseek', 'anthropic', 'openai', 'meta-llama', 'mistralai',
        'google', 'claude', 'gpt', 'llama', 'mixtral', 'cohere',
        'databricks', 'inflection', 'perplexity', 'microsoft',
        'nvidia', 'qwen', 'x-ai', 'xwin-lm', '01-ai', 'ai21',
        'amazon', 'openchat', 'teknium', 'gryphe', 'mancer',
        'cognitivecomputations', 'eva-unit-01', 'alpindale',
        'anthracite-org', 'sao10k', 'liquid', 'lizpreciatior',
        'neversleep', 'nousresearch', 'sophosympatheia',
        'nothingiisreal', 'infermatic', 'inflatebot', 'pygmalionai',
        'undi95', 'thedrummer', 'raifle', 'huggingfaceh4', 'openrouter',
        'deep infra', 'deepinfra', 'fireworks', 'together'
    }
    
    # Common words to filter out
    common_words = {
        'and', 'the', 'through', 'via', 'with', 'for', 'that',
        'apps', 'able', 'sample', 'versions', 'this', 'time',
        'from', 'by', 'provider', 'providers', 'available',
        'accessible', 'provided', 'using', 'model', 'models'
    }

    provider = model_path.split('/')[0].lower()
    model_name = model_path.split('/')[-1].lower()
    
    # Get model information from OpenRouter
    try:
        url = f"https://openrouter.ai/{provider}/{model_name}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            # Initialize provider info with default values
            provider_info = {
                'providers': [],
                'stats': {}
            }
            discovered_providers = set()

            # Add default provider
            provider_info['providers'].append(provider)
            provider_info['stats'][provider] = {
                'context': '32K tokens',
                'max_output': '4K tokens',
                'input_price': '$0.0005/1K tokens',
                'output_price': '$0.0005/1K tokens',
                'url': f'https://openrouter.ai/{provider}/{model_name}'
            }
            discovered_providers.add(provider)

            # Add known additional providers for specific models
            if model_name == 'deepseek-v3':
                additional_providers = ['fireworks', 'together']
                for p in additional_providers:
                    if p not in discovered_providers:
                        provider_info['providers'].append(p)
                        provider_info['stats'][p] = {
                            'context': '128K tokens',  # Specific to these providers
                            'max_output': '128K tokens',
                            'input_price': '$2.5/1K tokens',
                            'output_price': '$2.5/1K tokens',
                            'url': f'https://openrouter.ai/{provider}/{model_name}'
                        }
                        discovered_providers.add(p)

            # Parse the HTML content
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all provider blocks using multiple selectors
            provider_blocks = []
            for selector in [
                'div[class*="provider-block"]',
                'div[class*="provider-info"]',
                'div[class*="provider-details"]',
                'div[class*="model-provider"]'
            ]:
                blocks = soup.select(selector)
                provider_blocks.extend(blocks)
            
            # Also look for provider information in tables
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    for cell in cells:
                        if any(p in cell.get_text().lower() for p in known_providers):
                            provider_blocks.append(row)
            
            # Process each provider block
            for block in provider_blocks:
                # Get all text content
                stats_text = block.get_text()
                
                # Find provider name
                provider_found = False
                for known_provider in known_providers:
                    if known_provider in stats_text.lower():
                        provider_name = known_provider
                        if provider_name == 'deep infra':
                            provider_name = 'deepinfra'
                        provider_found = True
                        
                        # Extract stats with flexible patterns
                        context_match = re.search(r'(?:Context|Window|Size):\s*([0-9]+[KM])\s*(?:tokens|token|context)', stats_text, re.IGNORECASE)
                        max_output_match = re.search(r'(?:Max Output|Output Limit|Generation):\s*([0-9]+[KM])\s*(?:tokens|token)', stats_text, re.IGNORECASE)
                        input_price_match = re.search(r'(?:Input|Prompt|Context)(?:\s+Price)?:\s*\$([0-9.]+)(?:/1K tokens|/1k|/thousand)', stats_text, re.IGNORECASE)
                        output_price_match = re.search(r'(?:Output|Completion|Generation)(?:\s+Price)?:\s*\$([0-9.]+)(?:/1K tokens|/1k|/thousand)', stats_text, re.IGNORECASE)
                        latency_match = re.search(r'(?:Latency|Response Time|Speed):\s*([\d.]+)s', stats_text, re.IGNORECASE)
                        throughput_match = re.search(r'(?:Throughput|Rate):\s*([\d.]+)/ts', stats_text, re.IGNORECASE)
                        
                        if provider_name not in discovered_providers:
                            provider_info['providers'].append(provider_name)
                            discovered_providers.add(provider_name)
                            
                            provider_info['stats'][provider_name] = {
                                'context': f'{context_match.group(1) if context_match else "32K"} tokens',
                                'max_output': f'{max_output_match.group(1) if max_output_match else "4K"} tokens',
                                'input_price': f'${input_price_match.group(1) if input_price_match else "0.0005"}/1K tokens',
                                'output_price': f'${output_price_match.group(1) if output_price_match else "0.0005"}/1K tokens',
                                'latency': f'{latency_match.group(1)}s' if latency_match else None,
                                'throughput': f'{throughput_match.group(1)}/ts' if throughput_match else None,
                                'url': f'https://openrouter.ai/{provider}/{model_name}'
                            }
                        break
            
            # If no providers were found, use the original provider
            if not provider_info['providers']:
                provider_info['providers'] = [provider]
                provider_info['stats'][provider] = {
                    'context': '32K tokens',
                    'max_output': '4K tokens',
                    'input_price': '$0.0005/1K tokens',
                    'output_price': '$0.0005/1K tokens',
                    'url': f'https://openrouter.ai/{provider}/{model_name}'
                }
                discovered_providers = {provider}
    except Exception as e:
        logger.error(f"Error processing model {model_path}: {str(e)}")
        provider_info = {
            'providers': [provider],
            'stats': {
                provider: {
                    'context': '32K tokens',
                    'max_output': '4K tokens',
                    'input_price': '$0.0005/1K tokens',
                    'output_price': '$0.0005/1K tokens',
                    'url': f'https://openrouter.ai/{provider}/{model_name}'
                }
            }
        }
        discovered_providers = {provider}
    
    # Get additional details from API
    try:
        api_url = "https://openrouter.ai/api/v1/models"
        response = requests.get(api_url, headers={'Accept': 'application/json', **headers})
        if response.status_code == 200:
            data = response.json()
            for model in data.get('data', []):
                if model.get('id') == model_path:
                    # Update context length if available
                    context_tokens = model.get('context_length')
                    if context_tokens:
                        context_str = f'{context_tokens}K tokens' if context_tokens >= 1000 else f'{context_tokens} tokens'
                        for p in provider_info['stats']:
                            provider_info['stats'][p]['context'] = context_str
                    
                    # Update pricing if available
                    pricing = model.get('pricing', {})
                    if pricing:
                        input_price = pricing.get('input', 0)
                        output_price = pricing.get('output', 0)
                        for p in provider_info['stats']:
                            provider_info['stats'][p]['input_price'] = f'${input_price:.4f}/1K tokens'
                            provider_info['stats'][p]['output_price'] = f'${output_price:.4f}/1K tokens'
                    break
    except Exception as e:
        logger.error(f"Error fetching API data: {str(e)}")
    
    # Generate description
    provider_title = provider.title()
    providers_list = ', '.join([p.title() for p in provider_info['providers']])
    
    # Get max context length across providers
    max_context = '0K'
    for p_stats in provider_info['stats'].values():
        context = p_stats.get('context', '0K tokens')
        context_size = re.search(r'(\d+)K', context)
        if context_size:
            size = int(context_size.group(1))
            current_max = int(re.search(r'(\d+)K', max_context).group(1))
            if size > current_max:
                max_context = f'{size}K'
    
    # Model-specific descriptions
    descriptions = {
        'deepseek-chat': {
            'base': "Advanced conversational model optimized for natural dialogue and instruction following",
            'features': ["Strong performance in chat and conversation", "Efficient context handling", "Natural language understanding"]
        },
        'deepseek-coder': {
            'base': "Specialized coding model trained on high-quality programming data",
            'features': ["Code generation and completion", "Technical documentation", "Bug detection and fixing"]
        },
        'deepseek-math': {
            'base': "Advanced mathematical reasoning model designed for complex problem-solving",
            'features': ["Mathematical computation", "Equation solving", "Step-by-step explanations"]
        },
        'deepseek-v3': {
            'base': "Latest generation language model with enhanced capabilities",
            'features': ["Advanced reasoning", "Complex task handling", "Improved instruction following"]
        },
        'codellama': {
            'base': "Code-specialized model optimized for programming tasks",
            'features': ["Multi-language code generation", "Code analysis", "Technical documentation"]
        },
        'llama-2': {
            'base': "Advanced open-source language model with strong performance",
            'features': ["General-purpose capabilities", "Strong reasoning", "Safety-focused design"]
        },
        'claude': {
            'base': "Highly capable language model known for reasoning and safety",
            'features': ["Complex analysis", "Detailed explanations", "Safety considerations"]
        },
        'palm-2': {
            'base': "Advanced language model with strong multilingual capabilities",
            'features': ["Multilingual support", "Natural dialogue", "Knowledge integration"]
        },
        'mixtral': {
            'base': "Powerful mixture-of-experts model combining specialized networks",
            'features': ["Expert-based architecture", "Efficient processing", "Domain adaptation"]
        },
        'gpt-4': {
            'base': "State-of-the-art language model with exceptional reasoning",
            'features': ["Advanced reasoning", "Complex problem solving", "High accuracy"]
        },
        'gpt-3.5': {
            'base': "Efficient and capable model balancing performance and speed",
            'features': ["Fast processing", "Reliable outputs", "Cost-effective"]
        }
    }
    
    # Generate description with model-specific details
    model_info = None
    for key, info in descriptions.items():
        if key in model_name:
            model_info = info
            break
    
    if model_info:
        features_text = ', '.join(model_info['features'])
        description = (
            f"{model_info['base']} from {provider_title}. "
            f"Available through {providers_list} with up to {max_context} context window. "
            f"Key capabilities include {features_text}."
        )
    else:
        description = (
            f"Advanced language model from {provider_title}, available through {providers_list} "
            f"with up to {max_context} context window. Optimized for natural language understanding and generation."
        )
    
    return {
        'providers': provider_info['providers'],
        'provider_details': provider_info['stats'],
        'description': description
    }

def get_all_models():
    """Get all models from OpenRouter.ai API and web scraping"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    models = set()  # Use set to avoid duplicates
    
    # Try API first
    try:
        api_url = "https://openrouter.ai/api/v1/models"
        response = requests.get(api_url, headers={'Accept': 'application/json', **headers})
        response.raise_for_status()
        data = response.json()
        
        for model in data.get('data', []):
            model_id = model.get('id', '')
            if '/' in model_id:
                models.add(model_id)
    except Exception as e:
        logger.error(f"API error: {str(e)}")
    
    # Always do web scraping to catch any models not in API
    try:
        urls = [
            "https://openrouter.ai/docs",
            "https://openrouter.ai/models"
        ]
        
        for url in urls:
            try:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find model links in documentation
                for link in soup.find_all('a', href=re.compile(r'/(?:docs/)?models/[^/]+/[^/]+')):
                    href = link.get('href', '')
                    match = re.search(r'/(?:docs/)?models/([^/]+/[^/]+)', href)
                    if match:
                        model_path = match.group(1)
                        models.add(model_path)
                
                # Find models in script tags (for dynamic content)
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string:
                        matches = re.findall(r'["\']([^/"\'+]+/[^/"\'+]+)(?:/v\d+)?["\']', script.string)
                        for match in matches:
                            if any(provider in match.lower() for provider in [
                                'deepseek', 'anthropic', 'openai', 'meta-llama', 'mistralai',
                                'google', 'claude', 'gpt', 'llama', 'mixtral'
                            ]):
                                models.add(match)
            except Exception as e:
                logger.error(f"Error scraping {url}: {str(e)}")
                continue
    except Exception as e:
        logger.error(f"Web scraping error: {str(e)}")
    
    # Add known models that might be missed
    additional_models = [
        'deepseek/deepseek-chat',
        'deepseek/deepseek-coder',
        'deepseek/deepseek-math',
        'deepseek/deepseek-v3',
        'meta-llama/codellama-34b',
        'meta-llama/llama-2-70b',
        'anthropic/claude-2.1',
        'google/palm-2',
        'mistralai/mixtral-8x7b'
    ]
    
    for model in additional_models:
        models.add(model)
    
    models_list = sorted(list(models))
    logger.info(f"Found {len(models_list)} models")
    return models_list

def process_model(model_path):
    """Process a single model"""
    try:
        logger.info(f"Processing model: {model_path}")
        name = model_path.split('/')[-1].replace('-', ' ').title()
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
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
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