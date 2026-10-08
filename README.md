Smart Waste Management System — Static Demo

Files
- index.html — main static page
- styles.css — styling
- script.js — map init and small behaviors
- login.html — simple login placeholder

Google Maps API
1. Create or use an existing Google Cloud project and enable the Maps JavaScript API.
2. Create an API key and restrict it appropriately.
3. Replace `YOUR_API_KEY` in the script tag near the bottom of `index.html` with your key.

Local testing
- Open `index.html` in a browser (for Maps API you may need to serve over http(s) depending on key restrictions).
- To serve quickly from the project root run:

```bash
python3 -m http.server 8000
```

Then open http://localhost:8000 in your browser.

Geolocation
- The demo asks the browser for location permission and will auto-center and zoom to the user's location. Modern browsers require a secure context (HTTPS) for geolocation — `http://localhost` is allowed for local testing but deployment should use `https://`.
- The map has no geographic restrictions. Click `Use my location` to request permission and center the map on the device's current location.

Notes
- For production, restrict your API key by HTTP referrers and enable billing on your Google Cloud project as required by the Maps API.
