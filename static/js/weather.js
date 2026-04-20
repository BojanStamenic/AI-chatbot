/* ═══════════════════════════════════════════════════════════════
   SAT — real-time sat u sidebar footeru
   ═══════════════════════════════════════════════════════════════ */

const clockEl = document.getElementById("clockEl");

function startClock() {
  function tick() {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString("en-GB", { hour12: false });
  }
  tick();
  setInterval(tick, 1000);
}


/* ═══════════════════════════════════════════════════════════════
   VREMENSKA PROGNOZA — sidebar widget + WMO kodovi
   ═══════════════════════════════════════════════════════════════ */

const WMO = {
  0:  ["\u2600\uFE0F",  "Clear"],
  1:  ["\uD83C\uDF24",  "Mostly clear"],
  2:  ["\u26C5",  "Partly cloudy"],
  3:  ["\u2601\uFE0F",  "Overcast"],
  45: ["\uD83C\uDF2B",  "Foggy"],
  48: ["\uD83C\uDF2B",  "Icy fog"],
  51: ["\uD83C\uDF26",  "Light drizzle"],
  53: ["\uD83C\uDF26",  "Drizzle"],
  55: ["\uD83C\uDF27",  "Heavy drizzle"],
  61: ["\uD83C\uDF27",  "Light rain"],
  63: ["\uD83C\uDF27",  "Rain"],
  65: ["\uD83C\uDF27",  "Heavy rain"],
  71: ["\uD83C\uDF28",  "Light snow"],
  73: ["\uD83C\uDF28",  "Snow"],
  75: ["\u2744\uFE0F",  "Heavy snow"],
  77: ["\uD83C\uDF28",  "Snow grains"],
  80: ["\uD83C\uDF26",  "Showers"],
  81: ["\uD83C\uDF27",  "Rain showers"],
  82: ["\u26C8",  "Heavy showers"],
  85: ["\uD83C\uDF28",  "Snow showers"],
  86: ["\u2744\uFE0F",  "Heavy snow showers"],
  95: ["\u26C8",  "Thunderstorm"],
  96: ["\u26C8",  "Thunderstorm + hail"],
  99: ["\u26C8",  "Severe thunderstorm"],
};

const weatherEl = document.getElementById("weatherEl");
let localWeather = null;

async function fetchWeather() {
  try {
    let lat, lon, city;
    try {
      const r = await fetch("https://ipapi.co/json/");
      const d = await r.json();
      if (d.latitude) {
        lat  = d.latitude;
        lon  = d.longitude;
        city = d.city || d.region || "\u2014";
      }
    } catch (_) {}

    if (!lat) {
      const r = await fetch("http://ip-api.com/json");
      const d = await r.json();
      if (d.status === "success") {
        lat  = d.lat;
        lon  = d.lon;
        city = d.city || d.regionName || "\u2014";
      }
    }

    if (!lat) throw new Error("Could not determine location");

    const wRes = await fetch(
      "https://api.open-meteo.com/v1/forecast" +
      "?latitude=" + lat +
      "&longitude=" + lon +
      "&current=temperature_2m,apparent_temperature,weather_code,relative_humidity_2m,wind_speed_10m" +
      "&temperature_unit=celsius&timezone=auto"
    );
    const w = await wRes.json();

    const temp  = Math.round(w.current.temperature_2m);
    const feels = Math.round(w.current.apparent_temperature);
    const code  = w.current.weather_code;
    const [icon, desc] = WMO[code] || ["\uD83C\uDF21", "Unknown"];

    localWeather = {
      label:    city,
      temp, feels, desc,
      humidity: w.current.relative_humidity_2m,
      wind:     Math.round(w.current.wind_speed_10m)
    };

    weatherEl.innerHTML =
      icon + " <strong>" + temp + "\u00B0C</strong> \u00B7 " + desc +
      "<br>Feels " + feels + "\u00B0C \u00B7 \uD83D\uDCCD " + city;

    setTimeout(fetchWeather, 10 * 60 * 1000);
  } catch (err) {
    weatherEl.textContent = "Weather unavailable";
    console.warn("Weather fetch failed:", err);
  }
}


/* ═══════════════════════════════════════════════════════════════
   WEATHER ENRICHMENT — obogacuje chat poruke vremenskom prognozom
   ═══════════════════════════════════════════════════════════════ */

const WEATHER_KEYS = [
  "weather", "temperature", "forecast", "rain", "sunny", "cloudy",
  "snow", "wind", "humid", "vreme", "temperatura", "prognoza", "ki\u0161a", "sneg"
];

function looksLikeWeatherQuery(text) {
  const low = text.toLowerCase();
  return WEATHER_KEYS.some(function(k) { return low.includes(k); });
}

function extractCityFromQuery(text) {
  const m = text.match(
    /\b(?:in|for|at|u|na|za|about)\s+([A-Za-z\u00C0-\u00FF\u010D\u0107\u0111\u0161\u017E\u010C\u0106\u0110\u0160\u017D][A-Za-z\u00C0-\u00FF\u010D\u0107\u0111\u0161\u017E\u010C\u0106\u0110\u0160\u017D\s]{1,40}?)(?:\s*[?!.]?\s*$|\s+(?:right now|today|tonight|tomorrow|now|sada|danas|sutra))/i
  );
  return m ? m[1].trim() : null;
}

async function fetchWeatherForCity(cityName) {
  const geoRes = await fetch(
    "https://geocoding-api.open-meteo.com/v1/search?name=" +
    encodeURIComponent(cityName) + "&count=1&language=en&format=json"
  );
  const geo = await geoRes.json();
  if (!geo.results || !geo.results.length) return null;

  const place = geo.results[0];
  const label = [place.name, place.admin1, place.country].filter(Boolean).join(", ");

  const wRes = await fetch(
    "https://api.open-meteo.com/v1/forecast" +
    "?latitude=" + place.latitude +
    "&longitude=" + place.longitude +
    "&current=temperature_2m,apparent_temperature,weather_code,relative_humidity_2m,wind_speed_10m" +
    "&temperature_unit=celsius&timezone=auto"
  );
  const w    = await wRes.json();
  const c    = w.current;
  const [, desc] = WMO[c.weather_code] || ["", "Unknown"];

  return {
    label,
    temp:     Math.round(c.temperature_2m),
    feels:    Math.round(c.apparent_temperature),
    humidity: c.relative_humidity_2m,
    wind:     Math.round(c.wind_speed_10m),
    desc
  };
}

async function enrichWithWeather(text) {
  if (!looksLikeWeatherQuery(text)) return text;

  const city = extractCityFromQuery(text);
  let wd = null;

  if (city) {
    try { wd = await fetchWeatherForCity(city); } catch (_) {}
  }
  if (!wd && localWeather) {
    wd = localWeather;
  }
  if (!wd) return text;

  const ctx =
    "[Real-time weather data for " + wd.label + ": " +
    wd.temp + "\u00B0C, feels like " + wd.feels + "\u00B0C, " + wd.desc +
    ", humidity " + wd.humidity + "%, wind " + wd.wind + " km/h]";

  return ctx + "\n\n" + text;
}
