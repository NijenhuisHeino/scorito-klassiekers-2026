// Vercel Serverless Function: Fetch cycling news & match to riders
// Fetches RSS feeds, matches rider names, classifies injury severity, estimates missed races

const FEEDS = [
  { url: 'https://news.google.com/rss/search?q=wielrennen+blessure+voorjaarsklassieker+2026&hl=nl&gl=NL', name: 'Google News NL', lang: 'nl', type: 'rss' },
  { url: 'https://news.google.com/rss/search?q=cycling+injury+spring+classics+2026&hl=en', name: 'Google News EN', lang: 'en', type: 'rss' },
  { url: 'https://www.wielerflits.nl/feed/', name: 'WielerFlits', lang: 'nl', type: 'rss' },
  { url: 'https://sporza.be/nl/categorie/wielrennen.rss.xml', name: 'Sporza', lang: 'nl', type: 'atom' },
];

// Race calendar with dates (2026 season)
const RACE_CALENDAR = [
  { id: 'omloop',               date: '2026-02-28' },
  { id: 'kuurne',               date: '2026-03-01' },
  { id: 'strade-bianche',       date: '2026-03-07' },
  { id: 'paris-nice',           date: '2026-03-08' },
  { id: 'tirreno',              date: '2026-03-10' },
  { id: 'milano-sanremo',       date: '2026-03-21' },
  { id: 'e3',                   date: '2026-03-27' },
  { id: 'brugge',               date: '2026-03-28' },
  { id: 'gent-wevelgem',        date: '2026-03-29' },
  { id: 'dwars',                date: '2026-04-01' },
  { id: 'ronde-van-vlaanderen', date: '2026-04-05' },
  { id: 'scheldeprijs',         date: '2026-04-08' },
  { id: 'paris-roubaix',        date: '2026-04-12' },
  { id: 'brabantse-pijl',       date: '2026-04-16' },
  { id: 'amstel',               date: '2026-04-20' },
  { id: 'fleche-wallonne',      date: '2026-04-23' },
  { id: 'luik',                 date: '2026-04-27' },
];

// Severity classification keywords
const SEVERITY_LONG = [
  'fracture', 'fractuur', 'broken', 'breuk', 'gebroken',
  'surgery', 'operatie', 'collarbone', 'sleutelbeen',
  'pelvis', 'bekken', 'schouder', 'shoulder',
  'kruisband', 'acl', 'rest of season', 'rest van het seizoen',
  'maanden uit', 'months out', 'ruled out of spring',
];
const SEVERITY_MEDIUM = [
  'blessure', 'injury', 'injured', 'geblesseerd',
  'knee', 'knie', 'enkel', 'ankle', 'hamstring',
  'revalidatie', 'recovery', 'herstel', 'herstellende',
  'weken uit', 'weeks out', 'out for weeks',
];
const SEVERITY_SHORT = [
  'ziek', 'ziekte', 'illness', 'sick', 'niet fit', 'not fit',
  'griep', 'flu', 'verkouden', 'cold', 'koorts', 'fever',
  'onwel', 'unwell',
];
const SEVERITY_DNS = [
  'dns', 'niet aan de start', 'did not start',
  'uitvalt', 'afzegt', 'withdraw', 'opgave', 'abandon',
  'niet van start', 'will not start', 'mist',
];

// All injury keywords combined
const INJURY_KEYWORDS = [...SEVERITY_LONG, ...SEVERITY_MEDIUM, ...SEVERITY_SHORT, ...SEVERITY_DNS, 'crash', 'out of', 'ruled out'];

let riderNames = null;

async function loadRiderNames() {
  if (riderNames) return riderNames;
  const fs = require('fs');
  const path = require('path');
  const dataPath = path.join(process.cwd(), 'public', 'data.json');
  const raw = JSON.parse(fs.readFileSync(dataPath, 'utf-8'));
  riderNames = raw.riders
    .filter(r => r.numRaces > 0)
    .map(r => ({
      id: r.id, name: r.name,
      lastName: r.name.split(' ').slice(-1)[0],
      fullName: r.name.toLowerCase(),
      team: r.team,
    }));
  return riderNames;
}

function classifySeverity(text) {
  const t = text.toLowerCase();
  if (SEVERITY_LONG.some(kw => t.includes(kw))) return 'long';
  if (SEVERITY_MEDIUM.some(kw => t.includes(kw))) return 'medium';
  if (SEVERITY_SHORT.some(kw => t.includes(kw))) return 'short';
  if (SEVERITY_DNS.some(kw => t.includes(kw))) return 'dns';
  return 'unknown';
}

function getMissedRaces(severity, articleDate) {
  const now = articleDate ? new Date(articleDate) : new Date();
  const today = new Date();
  // Use the most recent date (article or today)
  const refDate = now > today ? today : (now.getTime() > 0 ? now : today);

  const daysOut = {
    long: 999,    // rest of season
    medium: 28,   // ~4 weeks
    short: 10,    // ~1.5 weeks
    dns: 3,       // just the next race
    unknown: 10,  // conservative default
  };

  const days = daysOut[severity] || 10;
  const returnDate = new Date(refDate);
  returnDate.setDate(returnDate.getDate() + days);

  const missed = [];
  for (const race of RACE_CALENDAR) {
    const raceDate = new Date(race.date);
    if (raceDate >= refDate && raceDate < returnDate) {
      missed.push(race.id);
    }
  }

  return { missedRaces: missed, returnDate: returnDate.toISOString().slice(0, 10) };
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
      title: cleanHtml(title).trim(), link: link.trim(),
      description: cleanHtml(desc).trim().slice(0, 300),
      date: pubDate.trim(), source: cleanHtml(source).trim(),
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
      title: cleanHtml(title).trim(), link: link.trim(),
      description: cleanHtml(desc).trim().slice(0, 300),
      date: pubDate.trim(), source: '',
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
      const nameMatch = text.includes(rider.fullName) ||
        (rider.lastName.length >= 4 && text.includes(rider.lastName.toLowerCase()));

      if (nameMatch) {
        matchedRiders.push(rider);
        const isInjury = INJURY_KEYWORDS.some(kw => text.includes(kw));
        const severity = isInjury ? classifySeverity(text) : null;

        if (!alerts[rider.id]) {
          alerts[rider.id] = {
            id: rider.id, name: rider.name, team: rider.team,
            status: isInjury ? 'warning' : 'news',
            severity: severity,
            missedRaces: [],
            returnDate: null,
            articles: [],
          };
        }

        // Track all severity mentions to pick the most common/appropriate one
        if (isInjury) {
          alerts[rider.id].status = 'warning';
          if (!alerts[rider.id]._severityCounts) alerts[rider.id]._severityCounts = {};
          const s = severity || 'unknown';
          alerts[rider.id]._severityCounts[s] = (alerts[rider.id]._severityCounts[s] || 0) + 1;
        }

        alerts[rider.id].articles.push({
          title: article.title, link: article.link,
          date: article.date, source: article.feedSource,
          isInjury, severity,
        });
      }
    }
    article.matchedRiders = matchedRiders.map(r => r.name);
  }

  // Post-process: determine final severity based on most frequent/severe classification
  for (const alert of Object.values(alerts)) {
    if (alert.status !== 'warning' || !alert._severityCounts) continue;
    const counts = alert._severityCounts;

    // If "long" keywords dominate (>50% of injury articles), use long
    // If "short" keywords dominate, use short (e.g., illness)
    // Otherwise use the highest severity that appears at least twice, or fallback to most frequent
    const total = Object.values(counts).reduce((s, c) => s + c, 0);
    const severityRank = { long: 4, medium: 3, short: 2, dns: 1, unknown: 0 };

    // Pick severity: if short (illness) is most frequent, prefer short over medium/long
    // This prevents "recovery" in a flu article from escalating to "long"
    let best = 'unknown';
    let bestCount = 0;
    for (const [sev, count] of Object.entries(counts)) {
      if (count > bestCount || (count === bestCount && severityRank[sev] > severityRank[best])) {
        best = sev; bestCount = count;
      }
    }

    // But if there's a clear "long" signal (fracture/surgery), that trumps frequency
    if (counts.long && counts.long >= 2) best = 'long';
    else if (counts.long === 1 && !counts.short && !counts.dns) best = 'long';

    alert.severity = best;

    // Get the most recent injury article date for calculating missed races
    const injuryArticles = alert.articles.filter(a => a.isInjury);
    const latestDate = injuryArticles.length > 0
      ? injuryArticles.sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0))[0].date
      : null;

    const { missedRaces, returnDate } = getMissedRaces(best, latestDate);
    alert.missedRaces = missedRaces;
    alert.returnDate = returnDate;
    delete alert._severityCounts;
  }

  return alerts;
}

export default async function handler(req, res) {
  try {
    const riders = await loadRiderNames();

    const feedResults = await Promise.allSettled(
      FEEDS.map(async (feed) => {
        const resp = await fetch(feed.url, {
          headers: { 'User-Agent': 'Mozilla/5.0 (compatible; ScoritoBot/1.0)' },
          signal: AbortSignal.timeout(8000),
        });
        if (!resp.ok) return { feed, items: [] };
        const xml = await resp.text();
        const items = feed.type === 'atom' ? parseAtom(xml) : parseRSS(xml);
        return { feed, items: items.map(item => ({ ...item, feedSource: feed.name, feedLang: feed.lang })) };
      })
    );

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

    allArticles.sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0));

    const seen = new Set();
    allArticles = allArticles.filter(a => {
      const key = a.title.toLowerCase().slice(0, 50);
      if (seen.has(key)) return false;
      seen.add(key); return true;
    });

    const riderAlerts = matchRiders(allArticles, riders);

    res.setHeader('Cache-Control', 's-maxage=900, stale-while-revalidate=1800');
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.status(200).json({
      articles: allArticles.slice(0, 50),
      riderAlerts,
      raceCalendar: RACE_CALENDAR,
      feedStatus,
      lastUpdated: new Date().toISOString(),
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
}
