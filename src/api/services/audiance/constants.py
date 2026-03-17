STOPWORDS = {
    "https",
    "http",
    "this",
    "that",
    "with",
    "have",
    "from",
    "your",
    "about",
    "если",
    "когда",
    "после",
    "через",
    "может",
    "только",
    "очень",
    "сегодня",
    "здесь",
    "потом",
    "their",
    "there",
    "which",
    "would",
    "could",
    "marketing",
    "telegram",
    "канал",
    "группа",
    "подписаться",
    "подписчик",
    "новый",
}

INTEREST_PATTERNS = {
    "marketing": (
        "маркет", "бренд", "реклам", "контент", "лид", "трафик", "охват",
        "воронк", "конверс", "smm", "crm", "таргет", "продвиж", "креатив",
        "копирайт", "посадоч", "лендинг", "перформ", "ugc", "инфлюенс",
        "seo", "sem", "retention", "cac", "ltv", "romi", "cpa", "cpc",
        "ctr", "email", "рассыл", "tone", "toneofvoice", "упаковк", "аудитор",
        "прогрев", "комьюнит", "reels", "stories", "рилс", "сторис",
        "telegramads", "ads", "adsmanager", "брендинг", "перфоманс", "медиаплан",
    ),
    "business": (
        "бизн", "компан", "продукт", "клиент", "рын", "стартап", "основател",
        "предпр", "управл", "операц", "стратег", "выруч", "юнит", "менедж",
        "масштаб", "b2b", "b2c", "юнитэконом", "прибыл", "монетиз", "gmv",
        "ebitda", "pnl", "финмодел", "ceo", "coo", "cpo", "roadmap", "роадмап",
        "команда", "найм", "процесс", "growth", "sales", "enterprise",
    ),
    "education": (
        "обуч", "курс", "урок", "вебинар", "универ", "школ", "студент",
        "знан", "навык", "карьер", "лекц", "ментор", "экзам", "учеб",
        "стажиров", "домашк", "семинар", "тьютор", "практик", "разбор",
        "гайд", "гид", "тренинг", "сертифик", "професс", "квалифик",
    ),
    "technology": (
        "ai", "ml", "python", "код", "разработ", "техн", "нейросет",
        "автомат", "it", "saas", "product", "digital", "данн", "алгоритм",
        "backend", "frontend", "devops", "api", "sdk", "docker", "kubernetes",
        "sql", "analytics", "git", "github", "openai", "llm", "prompt",
        "агент", "приложен", "сервер", "инфраструкт", "архитект", "cloud",
        "aws", "gcp", "azure", "typescript", "javascript", "react", "fastapi",
        "postgres", "redis", "nginx", "linux", "vps", "telegrambot", "бот",
    ),
    "media_lifestyle": (
        "музык", "фильм", "сериал", "путеш", "ед", "рецеп",
        "стил", "мод", "лайфст", "истор", "шоу", "культур",
        "интерв", "афиш", "концерт", "звезд", "селеб", "блогер",
        "мода", "лук", "гардероб", "ресторан", "кафе", "отдых", "туризм",
        "wellness", "здоров", "космет", "beauty", "уход", "психолог",
        "медиа", "блог", "блогеры", "инфлюенсер", "инфлюенс", "creator",
        "creators", "influencer", "influencers", "ютуб", "youtube", "ютубер",
        "тикток", "tiktok", "рилс", "reels", "шортс", "shorts", "подкаст",
        "podcast", "стример", "стримеры", "селебрити", "шоубиз",
    ),
    "news_current": (
        "новост", "срочн", "главн", "сегодня", "вчера", "дайджест", "обновл",
        "событ", "власт", "заяв", "прям", "репорт", "сводк", "телеграм",
        "полит", "президент", "премьер", "министр", "правитель", "госдум",
        "дум", "сенат", "парламент", "евросоюз", "нато", "санкц",
        "переговор", "выбор", "референдум", "дипломат", "посол", "мид",
        "саммит", "украин", "росси", "сша", "европ", "кремл", "киев",
        "израил", "иран", "газ", "орбан", "трамп", "байден", "путин",
        "эрдоган", "нетаньяху", "конфликт", "удар", "атака", "арм",
        "фронт", "военн", "оборон", "геополит", "междунар", "ormuz", "ормуз",
        "чп", "происшеств", "мобилиз", "минобор", "сводка", "мэр", "губернат",
        "повестка", "редакц", "редактор", "инсайд", "инсайдер", "breaking",
        "exclusive", "политика", "геополит", "международ", "оппозици",
        "чиновник", "совфед", "санкции", "переговоры", "выборы", "военкор",
        "обстрел", "минобороны", "мобилизация",
    ),
    "humor_memes": (
        "мем", "юмор", "шутк", "ирон", "смеш", "пранк", "прикол", "жиза",
        "угар", "ржа", "рофл", "сарказ", "стеб", "постирон", "lol",
        "кек", "мемас", "ору", "сатира", "фейл", "cringe", "кринж",
    ),
    "finance_crypto": (
        "крипт", "bitcoin", "btc", "eth", "трейд", "бирж", "инвест",
        "token", "blockchain", "финансы", "акци", "облигац", "капитал",
        "денег", "денеж", "эконом", "ставк", "инфляц", "цб", "банк",
        "валют", "рубл", "доллар", "евро", "дивиденд", "фонд", "портфел",
        "дефолт", "ликвид", "майнинг", "defi", "nft", "кэш", "налог",
        "moex", "nasdaq", "sp500", "s&p", "фьючерс", "опцион", "бонды", "ipo",
    ),
    "career_jobs": (
        "ваканс", "резюме", "собесед", "работ", "работодат", "hr", "рекрутер",
        "рекрут", "оффер", "зарплат", "удаленк", "фриланс", "стажиров",
        "найм", "headhunt", "hh", "linkedin", "cv", "career", "job",
        "vacancy", "joboffer", "talent", "talentacquisition", "релокац",
    ),
    "gaming": (
        "игр", "game", "gamer", "gaming", "playstation", "ps5", "xbox", "nintendo",
        "switch", "steamdeck", "игрок", "прохожд", "dlc", "геймплей", "gameplay",
        "донат", "скин", "скины", "battlepass", "battle", "quest", "craft",
        "minecraft", "fortnite", "genshin", "roblox", "honkai", "pubg", "warface",
        "elden", "wow", "warcraft", "cyberpunk", "among", "indie", "roguelike",
        "steam", "epicgames", "riot", "гайд", "билд", "патч", "обнова",
        "ивент", "season", "ranked", "mmr", "matchmaking", "coop", "loot",
    ),
    "sports_esports": (
        "спорт", "матч", "гол", "турнир", "чемпион", "лига", "команд",
        "тренер", "футбол", "хокке", "баскет", "теннис", "мма", "ufc",
        "киберспорт", "esports", "стример", "dota", "cs2", "valorant",
        "steam", "standoff", "league", "lol", "twitch", "стрим", "патч",
        "инт", "major", "лан", "рейтин", "квал", "frag", "ace",
        "faceit", "hltv", "blast", "pgl", "fissure", "dreamleague",
        "cs", "counterstrike", "counter-strike", "дота", "валорант", "стендофф",
        "киберспортсмен", "турик", "bo1", "bo3", "bo5", "mvp", "rifler", "awp",
        "entry", "support", "капитан", "roster", "lineup", "shuffle", "transfer",
        "qualifier", "playoff", "bracket", "navi", "spirit", "virtuspro", "vp",
        "g2", "faze", "mouz",
    ),
    "real_estate": (
        "недвиж", "квартир", "ипотек", "застрой", "жиль", "аренд", "дом",
        "жилк", "новострой", "коммерческ", "риелтор", "метр", "планиров",
        "недвижимость", "жк", "жилкомплекс", "апартамент", "девелопмент",
        "девелопер", "девелоперск", "новостройка", "квадратныйметр", "ипотека",
        "сдачаобъекта", "ключи", "котлован", "объект", "эксплуатац",
    ),
    "construction": (
        "строит", "стройк", "строй", "ремонт", "подряд", "подрядчик", "прораб",
        "архитект", "дизайнинтерьер", "дизайнпроект", "интерьер", "фасад", "бетон",
        "цемент", "кирпич", "монолит", "фундамент", "смет", "отделк", "инженерн",
        "коммуникац", "электромонтаж", "сантех", "кровл", "девелоп", "застройщик",
        "стройка", "строительство", "генподряд", "генподрядчик", "техзаказчик",
        "девелопер", "проектирован", "проектировщик", "архбюро", "архитектура",
        "рабочаядокументация", "черновая", "чистовая", "инженерка", "вентиляц",
        "отоплен", "водоснабж", "канализац", "электрика", "сантехника",
        "благоустрой", "стройматериал", "материалы", "арматура", "жби",
        "коттедж", "загородныйдом", "капремонт", "реконструкц", "сдачаобъекта",
    ),
    "auto_transport": (
        "авто", "машин", "тач", "автомоб", "перекуп", "подбор", "дтп",
        "осаго", "каско", "каршер", "трасс", "водител", "двигател", "мотор",
        "кузов", "пробег", "vin", "сто", "шиномонтаж", "парков", "бензин",
        "электромоб", "tesla", "bmw", "mercedes", "toyota", "lada",
        "geely", "chery", "haval", "kia", "hyundai", "ford", "audi",
    ),
    "medicine_health": (
        "мед", "врач", "доктор", "клиник", "здоров", "диагноз", "симптом",
        "лечение", "терап", "хирург", "педиатр", "психиатр", "психотерап",
        "фарма", "анализ", "витамин", "диета", "нутрици", "болезн", "иммун",
    ),
}

THEME_SUBTOPIC_PATTERNS = {
    "marketing": {
        "performance marketing": ("ads", "cpa", "cpc", "ctr", "traffic"),
        "content marketing": ("content", "ugc", "reels", "stories", "copy"),
        "brand marketing": ("brand", "branding", "creative", "media", "reach"),
    },
    "business": {
        "product growth": ("product", "growth", "roadmap", "gmv", "unit"),
        "operations": ("process", "ops", "manage", "team", "sales"),
        "entrepreneurship": ("startup", "founder", "ceo", "b2b", "enterprise"),
    },
    "education": {
        "courses": ("course", "lesson", "seminar", "training", "guide"),
        "career learning": ("career", "mentor", "skill", "practice", "intern"),
        "academic education": ("student", "school", "university", "exam", "study"),
    },
    "technology": {
        "ai and llm": ("ai", "llm", "prompt", "openai", "ml"),
        "software development": ("python", "backend", "frontend", "api", "sdk"),
        "infrastructure": ("docker", "kubernetes", "postgres", "cloud", "linux"),
    },
    "media_lifestyle": {
        "creator media": ("youtube", "tiktok", "podcast", "creator", "influencer"),
        "entertainment": ("music", "film", "serial", "show", "concert"),
        "lifestyle": ("beauty", "wellness", "travel", "style", "psychology"),
    },
    "news_current": {
        "politics": ("election", "sanction", "government", "president", "minister"),
        "international": ("nato", "eu", "conflict", "geopolit", "diplomat"),
        "breaking news": ("breaking", "digest", "report", "exclusive", "urgent"),
    },
    "humor_memes": {
        "memes": ("meme", "lol", "kek", "rofl", "joke"),
        "irony": ("irony", "sarcasm", "satire", "cringe", "fail"),
        "viral fun": ("fun", "viral", "laugh", "humor", "prank"),
    },
    "finance_crypto": {
        "crypto": ("bitcoin", "btc", "eth", "blockchain", "defi"),
        "investments": ("invest", "stock", "bond", "dividend", "portfolio"),
        "macro": ("inflation", "rate", "bank", "currency", "econom"),
    },
    "career_jobs": {
        "job search": ("vacancy", "resume", "cv", "joboffer", "interview"),
        "recruitment": ("hr", "recruit", "talent", "headhunt", "linkedin"),
        "career growth": ("salary", "career", "remote", "intern", "offer"),
    },
    "gaming": {
        "sandbox and building": ("minecraft", "sandbox", "creative", "build", "server", "city", "redstone"),
        "single-player games": ("story", "quest", "dlc", "indie", "roguelike", "gameplay"),
        "online games": ("battlepass", "matchmaking", "coop", "loot", "season", "genshin", "fortnite"),
    },
    "sports_esports": {
        "traditional sports": ("football", "hockey", "basket", "tennis", "ufc"),
        "esports tournaments": ("tournament", "major", "qualifier", "playoff", "bracket", "lan"),
        "pro teams": ("navi", "spirit", "virtuspro", "faze", "mouz", "roster"),
    },
    "real_estate": {
        "housing": ("apartment", "mortgage", "housing", "newbuild", "residential"),
        "development": ("developer", "construction", "project", "handover", "object"),
        "commercial property": ("commercial", "rent", "office", "meter", "realtor"),
    },
    "construction": {
        "building works": ("contractor", "foundation", "concrete", "estimate", "repair"),
        "engineering": ("ventilation", "heating", "electric", "plumbing", "water"),
        "materials": ("brick", "roof", "finish", "material", "cement"),
    },
    "auto_transport": {
        "cars": ("auto", "car", "mileage", "vin", "engine"),
        "brands": ("tesla", "bmw", "toyota", "lada", "geely"),
        "service": ("service", "tires", "parking", "road", "accident"),
    },
    "medicine_health": {
        "clinical": ("doctor", "clinic", "diagnosis", "treatment", "surgery"),
        "mental health": ("therapy", "psycho", "symptom", "psychi", "stress"),
        "preventive health": ("vitamin", "diet", "nutrition", "immune", "analysis"),
    },
}

INTEREST_PATTERNS["humor_memes"] = (
    "мем", "юмор", "шутк", "ирон", "смеш", "пранк", "прикол", "жиза",
    "угар", "ржа", "сарказ", "стеб", "постирон", "мемас", "ору",
    "сатира", "кринж", "самоирон", "щитпост", "разнос", "ор",
)

INTEREST_PATTERNS["sports_esports"] = (
    "спорт", "матч", "гол", "турнир", "чемпион", "лига", "команда",
    "тренер", "футбол", "хоккей", "баскет", "теннис", "мма", "ufc",
    "киберспорт", "esports", "стример", "dota", "cs2", "valorant",
    "standoff", "twitch", "стрим", "патч", "инт", "major", "лан",
    "рейтинг", "квал", "frag", "ace", "faceit", "hltv", "blast",
    "pgl", "fissure", "dreamleague", "cs", "counterstrike", "counter-strike",
    "дота", "валорант", "стендофф", "киберспортсмен", "турик", "bo1",
    "bo3", "bo5", "mvp", "rifler", "awp", "entry", "support",
    "капитан", "roster", "lineup", "shuffle", "transfer", "qualifier",
    "playoff", "bracket", "navi", "spirit", "virtuspro", "vp", "g2", "faze", "mouz",
)

THEME_SUBTOPIC_PATTERNS.update(
    {
        "marketing": {
            "performance marketing": ("ads", "cpa", "cpc", "ctr", "traffic", "трафик", "лид", "воронка"),
            "content marketing": ("content", "ugc", "reels", "stories", "copy", "контент", "креатив", "копирайт"),
            "brand marketing": ("brand", "branding", "creative", "media", "reach", "бренд", "охват", "упаковка"),
        },
        "business": {
            "product growth": ("product", "growth", "roadmap", "gmv", "unit", "продукт", "рост", "юнит"),
            "operations": ("process", "ops", "manage", "team", "sales", "процесс", "команда", "выручка"),
            "entrepreneurship": ("startup", "founder", "ceo", "b2b", "enterprise", "основатель", "бизнес", "предприниматель"),
        },
        "education": {
            "courses": ("course", "lesson", "seminar", "training", "guide", "курс", "урок", "вебинар"),
            "career learning": ("career", "mentor", "skill", "practice", "intern", "навык", "ментор", "стажировка"),
            "academic education": ("student", "school", "university", "exam", "study", "студент", "университет", "экзамен"),
        },
        "technology": {
            "ai and llm": ("ai", "llm", "prompt", "openai", "ml", "нейросеть", "промпт", "агент"),
            "software development": ("python", "backend", "frontend", "api", "sdk", "разработка", "код", "бот"),
            "infrastructure": ("docker", "kubernetes", "postgres", "cloud", "linux", "сервер", "инфра", "архитектура"),
        },
        "media_lifestyle": {
            "creator media": ("youtube", "tiktok", "podcast", "creator", "influencer", "ютуб", "рилс", "подкаст"),
            "entertainment": ("music", "film", "serial", "show", "concert", "музыка", "фильм", "сериал"),
            "lifestyle": ("beauty", "wellness", "travel", "style", "psychology", "лайфстайл", "уход", "путешествие"),
        },
        "news_current": {
            "politics": ("election", "sanction", "government", "president", "minister", "выборы", "санкции", "правительство"),
            "international": ("nato", "eu", "conflict", "geopolit", "diplomat", "геополитика", "переговоры", "конфликт"),
            "breaking news": ("breaking", "digest", "report", "exclusive", "urgent", "срочно", "сводка", "дайджест"),
        },
        "humor_memes": {
            "memes": ("meme", "мем", "мемас", "жиза", "ор", "ору", "щитпост"),
            "irony": ("irony", "sarcasm", "satire", "ирония", "сарказм", "постирония", "самоирония", "кринж"),
            "viral fun": ("viral", "humor", "prank", "юмор", "шутка", "прикол", "угар", "разнос"),
        },
        "finance_crypto": {
            "crypto": ("bitcoin", "btc", "eth", "blockchain", "defi", "крипта", "токен", "майнинг"),
            "investments": ("invest", "stock", "bond", "dividend", "portfolio", "инвестиции", "акции", "портфель"),
            "macro": ("inflation", "rate", "bank", "currency", "econom", "инфляция", "ставка", "валюта"),
        },
        "career_jobs": {
            "job search": ("vacancy", "resume", "cv", "joboffer", "interview", "вакансия", "резюме", "собеседование"),
            "recruitment": ("hr", "recruit", "talent", "headhunt", "linkedin", "рекрутер", "найм", "оффер"),
            "career growth": ("salary", "career", "remote", "intern", "offer", "зарплата", "карьера", "удаленка"),
        },
        "gaming": {
            "sandbox and building": ("minecraft", "sandbox", "creative", "build", "server", "city", "redstone", "майнкрафт", "сервер", "постройка"),
            "single-player games": ("story", "quest", "dlc", "indie", "roguelike", "gameplay", "сюжет", "прохождение", "одиночная"),
            "online games": ("battlepass", "matchmaking", "coop", "loot", "season", "genshin", "fortnite", "донат", "ивент", "катка"),
        },
        "sports_esports": {
            "traditional sports": ("football", "hockey", "basket", "tennis", "ufc", "футбол", "хоккей", "матч"),
            "esports tournaments": ("tournament", "major", "qualifier", "playoff", "bracket", "lan", "турнир", "мажор", "плейофф"),
            "pro teams": ("navi", "spirit", "virtuspro", "faze", "mouz", "состав", "квалификация", "киберспорт"),
        },
        "real_estate": {
            "housing": ("apartment", "mortgage", "housing", "newbuild", "residential", "квартира", "ипотека", "жк"),
            "development": ("developer", "construction", "project", "handover", "object", "застройщик", "стройка", "объект"),
            "commercial property": ("commercial", "rent", "office", "meter", "realtor", "аренда", "офис", "риелтор"),
        },
        "construction": {
            "building works": ("contractor", "foundation", "concrete", "estimate", "repair", "подрядчик", "фундамент", "смета"),
            "engineering": ("ventilation", "heating", "electric", "plumbing", "water", "отопление", "электрика", "водоснабжение"),
            "materials": ("brick", "roof", "finish", "material", "cement", "кирпич", "кровля", "отделка"),
        },
        "auto_transport": {
            "cars": ("auto", "car", "mileage", "vin", "engine", "авто", "пробег", "двигатель"),
            "brands": ("tesla", "bmw", "toyota", "lada", "geely", "киа", "хавал", "джили"),
            "service": ("service", "tires", "parking", "road", "accident", "сервис", "шины", "дтп"),
        },
        "medicine_health": {
            "clinical": ("doctor", "clinic", "diagnosis", "treatment", "surgery", "врач", "клиника", "диагноз"),
            "mental health": ("therapy", "psycho", "symptom", "psychi", "stress", "терапия", "психика", "стресс"),
            "preventive health": ("vitamin", "diet", "nutrition", "immune", "analysis", "витамин", "питание", "анализ"),
        },
    }
)

AGE_SIGNAL_WEIGHTS = {
    "13-17": {"media_lifestyle": 1.0, "technology": 0.6, "gaming": 1.1},
    "18-24": {"media_lifestyle": 1.2, "technology": 1.0, "education": 1.0, "marketing": 0.7, "gaming": 1.0, "sports_esports": 0.9},
    "25-34": {
        "business": 1.3,
        "marketing": 1.1,
        "technology": 0.9,
        "finance_crypto": 0.8,
        "news_current": 0.8,
        "education": 0.6,
        "career_jobs": 0.9,
        "gaming": 0.5,
        "auto_transport": 0.6,
    },
    "35-44": {
        "business": 1.0,
        "finance_crypto": 1.0,
        "marketing": 0.8,
        "news_current": 1.0,
        "media_lifestyle": 0.4,
        "real_estate": 0.8,
        "career_jobs": 0.7,
        "medicine_health": 0.7,
    },
    "45+": {
        "finance_crypto": 0.7,
        "business": 0.7,
        "news_current": 1.1,
        "media_lifestyle": 0.6,
        "real_estate": 0.9,
        "auto_transport": 0.8,
        "medicine_health": 0.8,
    },
}

PROFILE_AGE_SIGNAL_PATTERNS = {
    "13-17": (
        "школ", "лицей", "гимназ", "класс", "егэ", "огэ", "teen", "school",
        "школь", "подрост", "edits", "anime", "gamer",
    ),
    "18-24": (
        "студ", "универ", "колледж", "campus", "student", "college", "uni",
        "intern", "стаж", "бакалав", "магистр", "курс", "freshman",
    ),
    "25-34": (
        "маркет", "дизайн", "разраб", "dev", "product", "manager", "pm",
        "hr", "recruit", "smm", "agency", "предпр", "стартап", "аналит",
    ),
    "35-44": (
        "ceo", "founder", "owner", "директор", "руковод", "бизнес", "invest",
        "realty", "предприним", "эксперт", "consult", "coach",
    ),
    "45+": (
        "дед", "баб", "senior", "mentor", "настав", "семья", "family",
        "father", "mother", "tradition",
    ),
}

AGE_BUCKETS = (
    ("13-17", 13, 17),
    ("18-24", 18, 24),
    ("25-34", 25, 34),
    ("35-44", 35, 44),
    ("45+", 45, 120),
)

CONFIDENCE_LABELS = {
    "low": "низкая",
    "medium": "средняя",
    "high": "высокая",
}

ENTITY_TYPE_LABELS = {
    "channel": "канал",
    "supergroup": "супергруппа",
    "group": "группа",
    "channel_like": "канал",
}

THEME_LABELS = {
    "marketing": "маркетинг и продажи",
    "business": "бизнес и продукт",
    "education": "обучение и карьера",
    "technology": "технологии и AI",
    "media_lifestyle": "медиа и лайфстайл",
    "news_current": "новости и актуальная повестка",
    "humor_memes": "мемы и развлекательный контент",
    "finance_crypto": "финансы и крипто",
    "career_jobs": "карьера и вакансии",
    "gaming": "игры и гейминг",
    "sports_esports": "спорт и киберспорт",
    "real_estate": "недвижимость и девелопмент",
    "construction": "строительство и ремонт",
    "auto_transport": "авто и транспорт",
    "medicine_health": "медицина и здоровье",
}

KEY_TRANSLATIONS = {
    "high": "высокая_активность",
    "medium": "средняя_активность",
    "low": "низкая_активность",
    "unknown": "не_определено",
    "unavailable": "недостаточно_данных",
    "marketing": "маркетинг",
    "business": "бизнес",
    "education": "обучение",
    "technology": "технологии",
    "media_lifestyle": "медиа_и_лайфстайл",
    "news_current": "новости_и_повестка",
    "humor_memes": "мемы_и_развлечения",
    "finance_crypto": "финансы_и_крипто",
    "career_jobs": "карьера_и_вакансии",
    "gaming": "игры_и_гейминг",
    "sports_esports": "спорт_и_киберспорт",
    "real_estate": "недвижимость",
    "construction": "строительство",
    "auto_transport": "авто_и_транспорт",
    "medicine_health": "медицина_и_здоровье",
    "undetermined": "не_определено",
    "core_active": "ядро_активной_аудитории",
    "warm_audience": "теплая_аудитория",
    "silent_audience": "пассивная_аудитория",
    "bots": "боты",
}

GENERIC_THEME_KEYS = {
    "news_current",
    "media_lifestyle",
    "humor_memes",
}
