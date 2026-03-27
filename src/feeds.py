FEEDS = [
    {
        "name": "The Hacker News",
        "kind": "rss",
        "url": "https://feeds.feedburner.com/TheHackersNews",
    },
    {
        "name": "Krebs on Security",
        "kind": "rss",
        "url": "https://krebsonsecurity.com/feed/",
    },
    {
        "name": "BleepingComputer",
        "kind": "rss",
        "url": "https://www.bleepingcomputer.com/feed/",
    },
    {
        "name": "SecurityWeek",
        "kind": "rss",
        "url": "https://www.securityweek.com/feed/",
    },
    {
        "name": "Dark Reading",
        "kind": "rss",
        "url": "https://www.darkreading.com/rss.xml",
    },
    {
        "name": "CSO Online",
        "kind": "rss",
        "url": "https://www.csoonline.com/feed/",
    },
    {
        "name": "Infosecurity Magazine",
        "kind": "rss",
        "url": "https://www.infosecurity-magazine.com/rss/news/",
    },
    {
        "name": "CyberScoop",
        "kind": "rss",
        "url": "https://cyberscoop.com/feed/",
    },
    {
        "name": "The CyberWire",
        "kind": "html",
        "url": "https://thecyberwire.com/",
        "link_patterns": [
            r"https://thecyberwire\.com/newsletters/daily-briefing/\d+/\d+",
        ],
    },
    {
        "name": "安全内参",
        "kind": "html",
        "url": "https://www.secrss.com/",
        "link_patterns": [
            r"https://www\.secrss\.com/articles/\d+",
        ],
    },
    {
        "name": "安全客",
        "kind": "html",
        "url": "https://www.anquanke.com/",
        "link_patterns": [
            r"https://www\.anquanke\.com/post/id/\d+",
        ],
    },
    {
        "name": "CNCERT",
        "kind": "html",
        "url": "https://www.cert.org.cn/",
        "link_patterns": [
            r"https://www\.cert\.org\.cn/publish/main/(?:10|11|12|44|49|98)/\d{4}/\d+/\d+_\.html",
        ],
    },
]
