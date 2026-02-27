// Vercel Serverless Function: Fetch cycling news & match to riders
// Fetches RSS feeds from multiple sources, matches rider names, detects injury keywords

const FEEDS = [
  {
    url: 'https://news.google.com/rss/search?q=wielrennen+blessure+voorjaarsklassieker+2026&hl=nl&gl=NL',
    name: 'Google News NL',
    lang: 'nl',
    type: 'rss',
  },
  {
    url: 'https://news.google.com/rss/search?q=cycling+injury+spring+classics+2026&hl=en',
    name: 'Google News EN',
    lang: 'en',
    type: 'rss',
  },
  {
    url: 'https://www.wielerflits.nl/feed/',
    name: 'WielerFlits',
    lang: 'nl',
    type: 'rss',
  },
  {
    url: 'https://sporza.be/nl/categorie/wielrennen.rss.xml',
    name: 'Sporza',
    lang: 'nl',
    type: 'atom',
  },
];

const INJURY_KEYWORDS = [
  'blessure', 'geblesseerd', 'breuk', 'fractuur', 'ziek', 'ziekte',
  'niet aan de start', 'dns', 'uitvalt', 'opgave', 'afzegt',
  'injury', 'injured', 'fracture', 'broken', 'illness', 'sick',
  'ruled out', 'out of', 'did not start', 'withdraw', 'crash',
  'abandon', 'knee surgery', 'collarbone', 'sleutelbeen', 'operatie',
  'revalidatie', 'recovery', 'herstel', 'niet fit', 'not fit',
];

// Load rider names from static data.json at startup
let riderNames = null;

async function loadRiderNames() {
  if (riderNames) return riderNames;

  // Read the pre-built data.json
  const fs = require('fs');
  const path = require('path');
  const dataPath = path.join(process.cwd(), 'public', 'data.json');
  const raw = JSON.parse(fs.readFileSync(dataPath, 'utf-8'));

  riderNames = raw.riders
    .filter(r => r.numRaces > 0)
    .map(r => ({
      id: r.id,
      name: r.name,
      lastName: r.name.split(' ').slice(-1)[0],
      fullName: r.name.toLowerCase(),
      team: r.team,
    }));

  return riderNames;
}

function parseRSS(xml) {
  const items = [];
  const itemRegex = /<item>([\s\S]*?)<\/item>/gi;
  let match;
  while ((match = itemRegex.exec(xml)) !== null) {
    const block = match[1];
    const title = (block.match(/<title>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?<\/title>/) || [])[1] || '';
    const link = (block.match(/<link>([\s\S]*?)<\/link>/) || [])[1] || '';
    const desc = (block.match(/<description>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?<\/description>/) || [])[1] || '';
    const pubDate = (block.match(/<pubDate>([\s\S]*?)<\/pubDate>/) || [])[1] || '';
    const source = (block.match(/<source[^>]*>([\s\S]*?)<\/source>/) || [])[1] || '';
    items.push({
      title: cleanHtml(title).trim(),
      link: link.trim(),
      description: cleanHtml(desc).trim().slice(0, 300),
      date: pubDate.trim(),
      source: cleanHtml(source).trim(),
    });
  }
  return items;
}

function parseAtom(xml) {
  const items = [];
  const entryRegex = /<entry>([\s\S]*?)<\/entry>/gi;
  let match;
  while ((match = entryRegex.exec(xml)) !== null) {
    const block = match[1];
    const title = (block.match(/<title[^>]*>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?<\/title>/) || [])[1] || '';
    const link = (block.match(/<link[^>]*href="([^"]*)"/) || [])[1] || '';
    const desc = (block.match(/<(?:summary|content)[^>]*>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?<\/(?:summary|content)>/) || [])[1] || '';
    const pubDate = (block.match(/<(?:published|updated)>([\s\S]*?)<\/(?:published|updated)>/) || [])[1] || '';
    items.push({
      title: cleanHtml(title).trim(),
      link: link.trim(),
      description: cleanHtml(desc).trim().slice(0, 300),
      date: pubDate.trim(),
      source: '',
    });
  }
  return items;
}

function cleanHtml(str) {
  return str.replace(/<[^>]*>/g, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
}

function matchRiders(articles, riders) {
  const alerts = {};

  for (const article of articles) {
    const text = `${article.title} ${article.description}`.toLowerCase();
    const matchedRiders = [];

    for (const rider of riders) {
      // Match full name or last name (if last name is 4+ chars to avoid false positives)
      const nameMatch = text.includes(rider.fullName) ||
        (rider.lastName.length >= 4 && text.includes(rider.lastName.toLowerCase()));

      if (nameMatch) {
        matchedRiders.push(rider);

        // Check for injury keywords
        const isInjury = INJURY_KEYWORDS.some(kw => text.includes(kw));

        if (!alerts[rider.id]) {
          alerts[rider.id] = {
            id: rider.id,
            name: rider.name,
            team: rider.team,
            status: isInjury ? 'warning' : 'news',
            articles: [],
          };
        }

        // Upgrade status to warning if injury detected
        if (isInjury && alerts[rider.id].status !== 'warning') {
          alerts[rider.id].status = 'warning';
        }

        alerts[rider.id].articles.push({
          title: article.title,
          link: article.link,
          date: article.date,
          source: article.feedSource,
          isInjury,
        });
      }
    }

    article.matchedRiders = matchedRiders.map(r => r.name);
  }

  return alerts;
}

export default async function handler(req, res) {
  try {
    const riders = await loadRiderNames();

    // Fetch all feeds in parallel
    const feedResults = await Promise.allSettled(
      FEEDS.map(async (feed) => {
        const resp = await fetch(feed.url, {
          headers: { 'User-Agent': 'Mozilla/5.0 (compatible; ScoritoBot/1.0)' },
          signal: AbortSignal.timeout(8000),
        });
        if (!resp.ok) return { feed, items: [] };
        const xml = await resp.text();
        const items = feed.type === 'atom' ? parseAtom(xml) : parseRSS(xml);
        return {
          feed,
          items: items.map(item => ({ ...item, feedSource: feed.name, feedLang: feed.lang })),
        };
      })
    );

    // Collect all articles
    let allArticles = [];
    const feedStatus = [];
    for (const result of feedResults) {
      if (result.status === 'fulfilled' && result.value.items) {
        allArticles.push(...result.value.items);
        feedStatus.push({ name: result.value.feed.name, count: result.value.items.length, status: 'ok' });
      } else {
        feedStatus.push({ name: 'unknown', count: 0, status: 'error' });
      }
    }

    // Sort by date (newest first)
    allArticles.sort((a, b) => {
      const da = new Date(a.date || 0);
      const db = new Date(b.date || 0);
      return db - da;
    });

    // Deduplicate by title similarity
    const seen = new Set();
    allArticles = allArticles.filter(a => {
      const key = a.title.toLowerCase().slice(0, 50);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    // Match riders & detect injuries
    const riderAlerts = matchRiders(allArticles, riders);

    res.setHeader('Cache-Control', 's-maxage=900, stale-while-revalidate=1800');
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.status(200).json({
      articles: allArticles.slice(0, 50),
      riderAlerts,
      feedStatus,
      lastUpdated: new Date().toISOString(),
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
}
