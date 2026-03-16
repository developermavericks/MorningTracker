"""
Configuration for the NEXUS Scraper Engine.
Centralized keywords, regions, and search modifiers.
"""

SECTOR_KEYWORDS = {
    "artificial intelligence": [
        "AI", "Artificial Intelligence", "Machine Learning", "Deep Learning", "LLM", "Generative AI", "NLP",
        "Robotics", "Neural Networks", "AGI", "OpenAI", "Anthropic", "DeepMind", "Mistral", "Cohere",
        "Sam Altman", "Demis Hassabis", "Ilya Sutskever", "Geoffrey Hinton", "Yann LeCun", "Andrew Ng",
        "Jensen Huang", "NVIDIA AI", "Hugging Face", "ChatGPT", "Gemini", "Claude AI", "Llama 3", "GPT-5",
        "AI Safety", "AI Ethics", "Compute", "GPUs", "AI Startups", "AI Regulation", "AI Chips",
        "Stable Diffusion", "Midjourney", "DALL-E", "Runway AI", "Pika Labs", "Sora AI", "Groq AI",
        "TensorFlow", "PyTorch", "AutoGPT", "BabyAGI", "Vector Database", "Pinecone", "Milvus",
        "Prompt Engineering", "RAG", "Retrieval Augmented Generation", "Fine-tuning", "LoRA",
        "Q* Hypothesis", "Agentic Workflow", "AI Agents", "Perplexity AI", "Character.ai",
        "Inflection AI", "Scale AI", "Data Annotation", "RLHF", "Synthetic Data", "AI PC",
        "Copilot", "Azure AI", "AWS Bedrock", "Vertex AI", "Apple Intelligence", "X.AI", "Grok",
    ],
    "technology": [
        "Technology", "Software", "Hardware", "Cybersecurity", "Cloud Computing", "SaaS", "IoT", "5G",
        "Semiconductors", "Quantum Computing", "Metaverse", "Apple", "Microsoft", "Google", "Meta", "Amazon",
        "Intel", "AMD", "TSMC", "Tesla", "Tim Cook", "Satya Nadella", "Sundar Pichai", "Open Source",
        "Linux", "DevOps", "Web3", "AR/VR", "Silicon Valley", "Big Tech", "Data Privacy",
        "Cloud Native", "Kubernetes", "Docker", "Serverless", "Edge Computing", "Blockchain",
        "Ethereum", "Solana", "NFT", "Fintech", "Healthtech", "Proptech", "Edtech", "Adtech",
        "Zero Trust", "Ransomware", "EDR", "SOC", "Pentesting", "Web Security", "App Sec",
        "iPhone", "MacBook", "Vision Pro", "Android", "Pixel", "Windows 11", "Copilot PC",
        "ASML", "NVIDIA", "Broadcom", "Qualcomm", "Arm Holdings", "Data Centers", "GPU Clusters",
    ],
    "finance": [
        "Finance", "Banking", "Fintech", "Stock Market", "Investment", "Venture Capital", "Cryptocurrency",
        "Blockchain", "Economy", "Inflation", "GDP", "Interest Rates", "Goldman Sachs", "JPMorgan",
        "BlackRock", "Federal Reserve", "RBI", "SEBI", "Coinbase", "Warren Buffett", "Jamie Dimon",
        "NASDAQ", "NYSE", "Wall Street", "Digital Assets", "DeFi", "Central Bank", "Fiscal Policy",
        "Hedge Funds", "Private Equity", "M&A", "Investment Banking", "Mutual Funds", "ETFs",
        "Bull Market", "Bear Market", "Recession", "Quantitative Easing", "Debt Ceiling",
        "Stripe", "Plaid", "Adyen", "Revolut", "Visa", "Mastercard", "Crypto Exchange",
    ],
    "business": [
        "Business", "Corporate", "Merger", "Acquisition", "Startup", "Entrepreneur", "Revenue", "Retail",
        "Supply Chain", "Manufacturing", "IPO", "Valuation", "Funding", "Series A", "Series B",
        "Unicorn", "E-commerce", "Market Share", "Q1 Results", "Earnings Call", "Strategy", "CEO",
        "Founders", "Incubator", "Accelerator", "Logistics", "Direct-to-Consumer", "B2B", "B2C",
        "Gig Economy", "Remote Work", "Co-working", "Corporate Governance", "ESG", "Sustainability",
    ],
    "politics": [
        "Politics", "Government", "Election", "Policy", "Parliament", "Senate", "Diplomacy", "Geopolitics",
        "Democracy", "Legislation", "Cabinet", "Prime Minister", "President", "Foreign Policy",
        "Sanctions", "United Nations", "NATO", "Border Security", "Human Rights", "Public Policy",
        "White House", "Kremlin", "Downing Street", "European Union", "G7", "G20", "BRICS",
        "Trade War", "Tariffs", "Geopolitical Tension", "Election 2024", "Political Campaign",
    ],
    "health": [
        "Healthcare", "Medicine", "Hospital", "Pharma", "Biotech", "Vaccine", "Disease", "Mental Health",
        "Clinical Trial", "Drug Approval", "FDA", "WHO", "Public Health", "Oncology", "Genetics",
        "Longevity", "Biohacking", "Telemedicine", "MedTech", "Virology", "Pandemic",
        "Diabetes", "Immunotherapy", "CRISPR", "Gene Editing", "Neurology", "Cardiology",
        "Ozempic", "Wegovy", "Weight Loss Drugs", "Precision Medicine", "Aging Research",
    ],
    "environment": [
        "Climate Change", "Environment", "Sustainability", "Renewable Energy", "Carbon", "Pollution",
        "Solar", "Wind Energy", "EV", "Electric Vehicle", "Net Zero", "Green Energy", "COP", "IPCC",
        "Biodiversity", "Recycling", "Circular Economy", "Oceans", "Wildlife", "Conservation",
        "Carbon Credits", "Hydrogen Fuel", "Direct Air Capture", "Nuclear Fusion", "Grid Storage",
    ],
    "sports": [
        "Cricket", "Football", "IPL", "FIFA", "Olympics", "Tennis", "Basketball", "F1", "Formula 1",
        "Wimbledon", "Grand Slam", "Premier League", "Champions League", "BCCI", "Virat Kohli", "MS Dhoni",
        "NFL", "NBA", "Golf", "Athletics", "Sports Tech", "Transfer News",
        "World Cup", "Super Bowl", "Grand Prix", "E-sports", "Streaming Rights", "Sports Betting",
    ],
    "lifestyle": [
        "Lifestyle", "Wellness", "Fashion", "Travel", "Food", "Fitness", "Culture", "Luxury",
        "Entertainment", "Movies", "Music", "Celebrity", "Gaming", "Streaming", "Art", "Design",
        "Social Media", "Influencers", "Mental Wellbeing", "Hobbies", "Home Decor",
        "Netflix", "TikTok", "Instagram", "Pop Culture", "Gen Z Trends", "Digital Nomad",
    ],
    "education": [
        "Education", "University", "School", "EdTech", "Students", "Learning", "Academia",
        "Research", "STEM", "Scholarship", "Online Learning", "IIT", "IIM", "Higher Education",
        "K-12", "Vocational Training", "Literacy", "E-learning", "Scientific Papers",
        "Student Loans", "College Admissions", "Curriculum", "Pedagogy", "Lifelong Learning",
    ],
}

SEARCH_MODIFIERS = [
    "news", "latest", "update", "report", "analysis", "market", "policy", "regulation",
    "research", "innovation", "trending", "forecast", "announcement", "investment",
    "funding", "startup", "expert", "interview", "review", "growth", "challenge", "impact",
    "press release", "summit", "conference", "breakthrough", "scandal", "lawsuit",
    "acquisition", "merger", "partnership", "collaboration", "patent", "earnings",
    "exclusive", "leaked", "roadmap", "demo", "unveiled", "launched", "unveiling",
    "rumor", "speculation", "leak", "investigation", "case study", "white paper",
    "competitor", "market analysis", "regulatory filing", "insider", "perspective",
    "industry outlook", "quarterly results", "stock performance", "hiring", "layoffs",
    "expansion", "strategy shift", "disruption", "threat", "opportunity", "ranking",
    "top 10", "comparison", "feature", "profile", "investigative", "opinion",
]

REGION_MAP = {
    "global":    {"geo": "US", "cities": []},
    "india":     {"geo": "IN", "cities": ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad", "Surat", "Lucknow", "Indore", "Bhopal", "Patna", "Jaipur", "Chandigarh", "Kochi", "Gurgaon", "Noida"]},
    "usa":       {"geo": "US", "cities": ["New York", "San Francisco", "Washington", "Chicago", "Los Angeles", "Austin", "Seattle", "Boston", "Dallas", "Houston", "Miami", "Denver", "Atlanta", "Phoenix", "Philadelphia"]},
    "uk":        {"geo": "GB", "cities": ["London", "Manchester", "Birmingham", "Edinburgh", "Glasgow", "Liverpool", "Leeds", "Bristol"]},
    "canada":    {"geo": "CA", "cities": ["Toronto", "Vancouver", "Montreal", "Ottawa", "Calgary", "Edmonton", "Quebec City"]},
    "japan":     {"geo": "JP", "cities": ["Tokyo", "Osaka", "Kyoto", "Yokohama", "Nagoya", "Sapporo", "Fukuoka"]},
    "australia": {"geo": "AU", "cities": ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Canberra", "Gold Coast"]},
    "europe":    {"geo": "EU", "cities": ["Berlin", "Paris", "Madrid", "Rome", "Amsterdam", "Brussels", "Vienna", "Zurich", "Stockholm", "Dublin"]},
}

INDIAN_LANGUAGES = [
    {"name": "Hindi", "code": "hi-IN", "ceid": "IN:hi"},
    {"name": "Bengali", "code": "bn", "ceid": "IN:bn"},
    {"name": "Marathi", "code": "mr-IN", "ceid": "IN:mr"},
    {"name": "Telugu", "code": "te-IN", "ceid": "IN:te"},
    {"name": "Tamil", "code": "ta-IN", "ceid": "IN:ta"},
    {"name": "Gujarati", "code": "gu-IN", "ceid": "IN:gu"},
    {"name": "Kannada", "code": "kn-IN", "ceid": "IN:kn"},
    {"name": "Malayalam", "code": "ml-IN", "ceid": "IN:ml"},
    {"name": "Punjabi", "code": "pa-IN", "ceid": "IN:pa"},
    {"name": "English (India)", "code": "en-IN", "ceid": "IN:en"}
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
]
