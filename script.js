// Start the application after Google Maps finishes loading.
function initMap(){
  // Use a fallback center until the browser returns the device location.
  const defaultCenter = { lat: 16.833944, lng: 81.531444 }; // 16°50'02.2"N 81°31'53.2"E

  // Create an unrestricted map and allow normal mouse-wheel zooming.
  const map = new google.maps.Map(document.getElementById('map'), {
    center: defaultCenter,
    zoom: 12,
    gestureHandling: 'greedy',
    // Hide Google's built-in points of interest so only custom legend markers appear.
    styles: [
      {
        featureType: 'poi',
        elementType: 'labels',
        stylers: [{ visibility: 'off' }]
      },
      {
        featureType: 'transit',
        elementType: 'labels',
        stylers: [{ visibility: 'off' }]
      }
    ]
  });

  // Track whether the first location fix has been received.
  let firstFix = true;

  // Create the teal marker that represents the device location.
  const userMarker = new google.maps.Marker({
    position: defaultCenter,
    map,
    title: 'Your location',
    icon: {
      path: google.maps.SymbolPath.CIRCLE,
      scale: 8,
      fillColor: '#0aa3a3',
      fillOpacity: 1,
      strokeColor: '#fff',
      strokeWeight: 2
    }
  });

  // Find all controls and output areas used by the map interface.
  const locateBtn = document.getElementById('locate-btn');
  const locationStatus = document.getElementById('location-status');
  const routeStatus = document.getElementById('route-status');
  const addLegendBtn = document.getElementById('add-legend-btn');
  const markPolygonBtn = document.getElementById('mark-polygon-btn');
  const finishPolygonBtn = document.getElementById('finish-polygon-btn');
  const clearPolygonBtn = document.getElementById('clear-polygon-btn');
  const polygonStatus = document.getElementById('polygon-status');
  const legendForm = document.getElementById('legend-form');
  const cancelLegendBtn = document.getElementById('cancel-legend-btn');
  const legendList = document.getElementById('legend-list');
  const legendStatus = document.getElementById('legend-status');
  const legendCount = document.getElementById('legend-count');
  const nearestLegend = document.getElementById('nearest-legend');
  const routeSummary = document.getElementById('route-summary');
  // Load saved locations before creating their markers.
  const savedLegends = loadLegends();
  // Keep marker objects separate from saved data so markers can be removed later.
  const legendMarkers = new Map();
  // Track the temporary point selected while a new legend is being created.
  let selectingLegendLocation = false;
  let selectedLegendLocation = null;
  let selectedLegendMarker = null;
  let currentPosition = null;
  let markingPolygon = false;
  let polygonPoints = [];
  let polygonMarkers = [];
  let markedPolygon = null;
  let outsidePolygonMask = null;
  let polygonEditingLocked = false;
  // Create the Google services used to calculate and draw routes.
  const directionsService = new google.maps.DirectionsService();
  const directionsRenderer = new google.maps.DirectionsRenderer({ map });

  function loadLegends(){
    // Read the saved JSON list from this website's browser storage.
    try{
      const saved = JSON.parse(localStorage.getItem('swms_map_legends') || '[]');
      // Reject invalid storage values instead of breaking map initialization.
      return Array.isArray(saved) ? saved : [];
    }catch(error){
      return [];
    }
  }

  function saveLegends(){
    // Persist the complete list so it can be restored on the next visit.
    try{
      localStorage.setItem('swms_map_legends', JSON.stringify(savedLegends));
    }catch(error){
      console.warn('Unable to save map legends:', error);
    }
  }

  function setPolygonStatus(text){
    if(polygonStatus) polygonStatus.textContent = text;
  }

  function lockPolygonEditing(){
    // A completed polygon becomes read-only for later visits and interactions.
    polygonEditingLocked = true;
    markPolygonBtn.hidden = true;
    finishPolygonBtn.hidden = true;
    clearPolygonBtn.hidden = true;
  }

  function clearMarkedPolygon(){
    polygonMarkers.forEach(function(marker){ marker.setMap(null); });
    polygonMarkers = [];
    if(markedPolygon){
      markedPolygon.setMap(null);
      markedPolygon = null;
    }
    polygonPoints = [];
    setPolygonStatus('');
  }

  function finishPolygon(){
    if(polygonPoints.length < 3){
      setPolygonStatus('Select at least three points to create a polygon.');
      return;
    }
    markedPolygon = new google.maps.Polygon({
      paths: polygonPoints,
      strokeColor: '#1976d2',
      strokeOpacity: 0.9,
      strokeWeight: 2,
      fillColor: '#1976d2',
      fillOpacity: 0.15,
      clickable: false,
      map
    });
    drawOutsidePolygonMask(polygonPoints);
    fitMapToPolygon(polygonPoints);
    savePolygonPoints(polygonPoints);
    markingPolygon = false;
    lockPolygonEditing();
    setPolygonStatus('Polygon marked with ' + polygonPoints.length + ' points.');
  }

  function loadSavedPolygon(){
    // Restore the completed polygon from browser storage.
    try{
      const saved = JSON.parse(localStorage.getItem('swms_marked_polygon') || 'null');
      return Array.isArray(saved) && saved.length >= 3 ? saved : null;
    }catch(error){
      return null;
    }
  }

  function drawSavedPolygon(points){
    // Display the saved polygon as a read-only map overlay.
    markedPolygon = new google.maps.Polygon({
      paths: points,
      strokeColor: '#1976d2',
      strokeOpacity: 0.9,
      strokeWeight: 2,
      fillColor: '#1976d2',
      fillOpacity: 0.15,
      clickable: false,
      map
    });
    drawOutsidePolygonMask(points);
    fitMapToPolygon(points);
  }

  function fitMapToPolygon(points){
    const bounds = new google.maps.LatLngBounds();
    points.forEach(function(point){ bounds.extend(point); });
    map.fitBounds(bounds, 48);
  }

  function isInsidePolygon(point, points){
    // Use ray casting to determine whether a coordinate is inside the saved polygon.
    let inside = false;
    for(let index = 0, previous = points.length - 1; index < points.length; previous = index++){
      const currentPoint = points[index];
      const previousPoint = points[previous];
      const crossesLatitude = (currentPoint.lat > point.lat) !== (previousPoint.lat > point.lat);
      const crossingLongitude = (previousPoint.lng - currentPoint.lng)
        * (point.lat - currentPoint.lat) / (previousPoint.lat - currentPoint.lat)
        + currentPoint.lng;
      if(crossesLatitude && point.lng < crossingLongitude) inside = !inside;
    }
    return inside;
  }

  function drawOutsidePolygonMask(points){
    if(outsidePolygonMask) outsidePolygonMask.setMap(null);
    class OutsidePolygonBlurOverlay extends google.maps.OverlayView {
      onAdd(){
        this.container = document.createElement('div');
        this.container.className = 'outside-polygon-blur';
        this.container.innerHTML = '<svg aria-hidden="true"><defs><mask id="selected-area-mask"><rect width="100%" height="100%" fill="white"></rect><path class="selected-area-cutout" fill="black"></path></mask></defs><foreignObject width="100%" height="100%" mask="url(#selected-area-mask)"><div class="outside-polygon-blur-layer"></div></foreignObject></svg>';
        map.getDiv().appendChild(this.container);
      }

      draw(){
        const projection = this.getProjection();
        const mapDiv = map.getDiv();
        const width = mapDiv.clientWidth;
        const height = mapDiv.clientHeight;
        const path = points.map(function(point, index){
          const pixel = projection.fromLatLngToContainerPixel(new google.maps.LatLng(point.lat, point.lng));
          return (index ? 'L' : 'M') + pixel.x + ' ' + pixel.y;
        }).join(' ') + ' Z';
        this.container.style.width = width + 'px';
        this.container.style.height = height + 'px';
        this.container.querySelector('svg').setAttribute('viewBox', '0 0 ' + width + ' ' + height);
        this.container.querySelector('.selected-area-cutout').setAttribute('d', path);
      }

      onRemove(){
        this.container.remove();
      }
    }
    outsidePolygonMask = new OutsidePolygonBlurOverlay();
    outsidePolygonMask.setMap(map);
  }

  function savePolygonPoints(points){
    // Persist polygon vertices so the read-only overlay survives reloads.
    try{
      localStorage.setItem('swms_marked_polygon', JSON.stringify(points));
    }catch(error){
      console.warn('Unable to save marked polygon:', error);
    }
  }

  const savedPolygon = loadSavedPolygon();
  if(savedPolygon){
    drawSavedPolygon(savedPolygon);
    lockPolygonEditing();
    // Permanently remove any saved legends that are outside the polygon.
    const insideLegends = savedLegends.filter(function(legend){
      return isInsidePolygon(legend, savedPolygon);
    });
    if(insideLegends.length !== savedLegends.length){
      savedLegends.splice(0, savedLegends.length, ...insideLegends);
      saveLegends();
    }
  }
  window.addEventListener('beforeunload', function(){
    // Preserve an existing in-memory polygon before the page closes.
    if(markedPolygon){
      const points = markedPolygon.getPath().getArray().map(function(point){
        return { lat: point.lat(), lng: point.lng() };
      });
      if(points.length >= 3) savePolygonPoints(points);
    }
  });


  function markerIcon(){
    // Use an orange circular icon for saved waste locations.
    return {
      path: google.maps.SymbolPath.CIRCLE,
      scale: 8,
      fillColor: '#f28c28',
      fillOpacity: 1,
      strokeColor: '#fff',
      strokeWeight: 2
    };
  }

  function setRouteStatus(text){
    // Display route progress or errors below the map.
    if(routeStatus) routeStatus.textContent = text;
  }

  function distanceBetweenPoints(first, second){
    // Calculate straight-line distance using the Haversine formula.
    const earthRadius = 6371;
    const toRadians = function(value){ return value * Math.PI / 180; };
    const latitudeDifference = toRadians(second.lat - first.lat);
    const longitudeDifference = toRadians(second.lng - first.lng);
    const latitudeOne = toRadians(first.lat);
    const latitudeTwo = toRadians(second.lat);
    const value = Math.sin(latitudeDifference / 2) ** 2
      + Math.cos(latitudeOne) * Math.cos(latitudeTwo) * Math.sin(longitudeDifference / 2) ** 2;
    return earthRadius * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
  }

  function formatDistance(distanceInKilometers){
    // Use meters for nearby points and kilometers for longer distances.
    return distanceInKilometers < 1
      ? Math.round(distanceInKilometers * 1000) + ' m away'
      : distanceInKilometers.toFixed(1) + ' km away';
  }

  function updateLegendStats(legendsToDisplay){
    // Refresh the count and nearest-location summary beneath the map.
    if(legendCount) legendCount.textContent = savedLegends.length;
    if(nearestLegend){
      nearestLegend.textContent = currentPosition && legendsToDisplay.length
        ? legendsToDisplay[0].name + ' (' + formatDistance(distanceBetweenPoints(currentPosition, legendsToDisplay[0])) + ')'
        : 'None';
    }
  }

  function navigateToLegend(legend){
    // Use the latest GPS position as the route origin.
    const origin = currentPosition || userMarker.getPosition();
    if(!currentPosition){
      setRouteStatus('Getting your current location...');
      requestCurrentLocation(function(){ navigateToLegend(legend); });
      return;
    }
    // Ask Google for the best available driving route to this saved location.
    setRouteStatus('Calculating route...');
    directionsService.route({
      origin,
      destination: { lat: legend.lat, lng: legend.lng },
      travelMode: google.maps.TravelMode.DRIVING,
      provideRouteAlternatives: false,
      optimizeWaypoints: true,
      drivingOptions: {
        departureTime: new Date(),
        trafficModel: 'bestguess'
      }
    }, function(result, status){
      if(status === 'OK'){
        // Draw the returned route on the map.
        directionsRenderer.setDirections(result);
        // Read the first route leg to show distance and estimated travel time.
        const routeLeg = result.routes[0] && result.routes[0].legs[0];
        const routeDetails = routeLeg && routeLeg.distance && routeLeg.duration
          ? routeLeg.distance.text + ', ' + routeLeg.duration.text
          : 'Details unavailable';
        if(routeSummary) routeSummary.textContent = routeDetails;
        setRouteStatus('Best driving route to ' + legend.name + ' displayed.');
      }else{
        if(routeSummary) routeSummary.textContent = 'No route selected';
        setRouteStatus('Unable to calculate a route: ' + status + '.');
      }
    });
  }

  function renderLegendList(){
    // Rebuild the saved-location list whenever data or the user location changes.
    legendList.innerHTML = '';
    // Sort a copy so the saved storage order is not changed.
    const savedPolygon = loadSavedPolygon();
    const legendsToDisplay = savedLegends.filter(function(legend){
      return !savedPolygon || isInsidePolygon(legend, savedPolygon);
    }).sort(function(first, second){
      if(!currentPosition) return 0;
      return distanceBetweenPoints(currentPosition, first) - distanceBetweenPoints(currentPosition, second);
    });
    updateLegendStats(legendsToDisplay);
    // Create one list row and its actions for every saved location.
    legendsToDisplay.forEach(function(legend){
      const item = document.createElement('div');
      item.className = 'legend-item';
      item.innerHTML = '<div><strong></strong><small></small><span class="legend-distance"></span></div><div><button type="button" class="nav-link navigate-legend-btn" style="background:var(--accent);color:#fff">Navigate</button><button type="button" class="nav-link delete-legend-btn" style="background:white;color:var(--text)">Delete</button></div>';
      item.querySelector('strong').textContent = legend.name;
      item.querySelector('small').textContent = legend.category + (legend.description ? ' - ' + legend.description : '');
      item.querySelector('.legend-distance').textContent = currentPosition
        ? formatDistance(distanceBetweenPoints(currentPosition, legend))
        : 'Distance unavailable until location is found';
      // Start route calculation when the row's Navigate button is clicked.
      item.querySelector('.navigate-legend-btn').addEventListener('click', function(){
        navigateToLegend(legend);
      });
      // Remove both the saved record and its map marker when Delete is clicked.
      item.querySelector('.delete-legend-btn').addEventListener('click', function(){
        const marker = legendMarkers.get(legend.id);
        if(marker) marker.setMap(null);
        legendMarkers.delete(legend.id);
        savedLegends.splice(savedLegends.indexOf(legend), 1);
        saveLegends();
        renderLegendList();
      });
      legendList.appendChild(item);
    });
  }

  function addLegendMarker(legend){
    const savedPolygon = loadSavedPolygon();
    if(savedPolygon && !isInsidePolygon(legend, savedPolygon)) return;
    // Place one orange marker at the saved latitude and longitude.
    const marker = new google.maps.Marker({
      position: { lat: legend.lat, lng: legend.lng },
      map,
      title: legend.name,
      icon: markerIcon()
    });
    // Prepare a popup containing the location details and navigation action.
    const infoWindow = new google.maps.InfoWindow({
      content: '<strong></strong><br><span></span>'
    });
    infoWindow.getContent();
    // Build popup elements safely with textContent instead of raw user HTML.
    const content = document.createElement('div');
    const title = document.createElement('strong');
    const details = document.createElement('span');
    const navigateButton = document.createElement('button');
    title.textContent = legend.name;
    details.textContent = legend.category + (legend.description ? ' - ' + legend.description : '');
    navigateButton.type = 'button';
    navigateButton.textContent = 'Navigate here';
    navigateButton.style.cssText = 'display:block;margin-top:8px;padding:5px 8px;cursor:pointer';
    navigateButton.addEventListener('click', function(){ navigateToLegend(legend); });
    content.append(title, document.createElement('br'), details, navigateButton);
    infoWindow.setContent(content);
    // Open the popup when the saved marker is selected.
    marker.addListener('click', function(){ infoWindow.open({ map, anchor: marker }); });
    legendMarkers.set(legend.id, marker);
  }

  // Restore every saved marker when the map opens.
  savedLegends.forEach(addLegendMarker);
  // Render the saved list and initial statistics.
  renderLegendList();


  // Enter map-selection mode when the user starts adding a legend.
  addLegendBtn && addLegendBtn.addEventListener('click', function(){
    if(markingPolygon) return;
    if(selectedLegendMarker) selectedLegendMarker.setMap(null);
    selectingLegendLocation = true;
    selectedLegendLocation = null;
    legendForm.hidden = false;
    legendStatus.textContent = 'Click anywhere on the map to choose the legend location.';
    addLegendBtn.disabled = true;
  });

  // Start collecting polygon vertices from map clicks.
  markPolygonBtn && markPolygonBtn.addEventListener('click', function(){
    if(selectingLegendLocation || polygonEditingLocked) return;
    clearMarkedPolygon();
    markingPolygon = true;
    markPolygonBtn.disabled = true;
    finishPolygonBtn.hidden = false;
    clearPolygonBtn.hidden = false;
    setPolygonStatus('Click points on the map, then choose Finish polygon.');
  });

  // Finish the polygon after the user has selected its vertices.
  finishPolygonBtn && finishPolygonBtn.addEventListener('click', finishPolygon);

  // Remove the current polygon and its temporary vertex markers.
  clearPolygonBtn && clearPolygonBtn.addEventListener('click', function(){
    clearMarkedPolygon();
    markingPolygon = false;
    finishPolygonBtn.hidden = true;
    clearPolygonBtn.hidden = true;
    markPolygonBtn.disabled = false;
  });

  // Capture the next map click as the new legend coordinates.
  map.addListener('click', function(event){
    if(markingPolygon){
      const point = { lat: event.latLng.lat(), lng: event.latLng.lng() };
      polygonPoints.push(point);
      polygonMarkers.push(new google.maps.Marker({
        position: point,
        map,
        title: 'Polygon point ' + polygonPoints.length,
        label: String(polygonPoints.length)
      }));
      setPolygonStatus(polygonPoints.length + ' polygon point(s) selected.');
      return;
    }
    if(!selectingLegendLocation) return;
    const savedPolygon = loadSavedPolygon();
    if(savedPolygon && !isInsidePolygon(event.latLng.toJSON(), savedPolygon)){
      legendStatus.textContent = 'Legends can only be added inside the marked polygon.';
      return;
    }
    selectedLegendLocation = {
      lat: event.latLng.lat(),
      lng: event.latLng.lng()
    };
    if(selectedLegendMarker) selectedLegendMarker.setMap(null);
    // Show a temporary blue marker so the selected point is visible.
    selectedLegendMarker = new google.maps.Marker({
      position: selectedLegendLocation,
      map,
      title: 'Selected legend location',
      icon: {
        path: google.maps.SymbolPath.CIRCLE,
        scale: 9,
        fillColor: '#1976d2',
        fillOpacity: 0.95,
        strokeColor: '#fff',
        strokeWeight: 3
      }
    });
    selectingLegendLocation = false;
    legendStatus.textContent = 'Location selected. Blue pin marks the selected point.';
  });

  // Cancel selection and remove the temporary marker.
  cancelLegendBtn && cancelLegendBtn.addEventListener('click', function(){
    if(selectedLegendMarker) selectedLegendMarker.setMap(null);
    selectedLegendMarker = null;
    legendForm.reset();
    legendForm.hidden = true;
    selectingLegendLocation = false;
    selectedLegendLocation = null;
    addLegendBtn.disabled = false;
  });

  // Validate and save the form after the user has selected a map point.
  legendForm.addEventListener('submit', function(event){
    event.preventDefault();
    if(!selectedLegendLocation){
      legendStatus.textContent = 'Select a location on the map first.';
      return;
    }
    // Combine form values and map coordinates into one saved record.
    const legend = {
      id: Date.now().toString(),
      name: document.getElementById('legend-name').value.trim(),
      category: document.getElementById('legend-category').value,
      description: document.getElementById('legend-description').value.trim(),
      lat: selectedLegendLocation.lat,
      lng: selectedLegendLocation.lng
    };
    // Save the record, replace the temporary marker, and refresh the list.
    savedLegends.push(legend);
    saveLegends();
    if(selectedLegendMarker) selectedLegendMarker.setMap(null);
    selectedLegendMarker = null;
    addLegendMarker(legend);
    renderLegendList();
    legendForm.reset();
    legendForm.hidden = true;
    selectedLegendLocation = null;
    addLegendBtn.disabled = false;
  });

  // Display location permission and GPS status below the map.
  function setLocationStatus(text){
    if(locationStatus) locationStatus.textContent = text;
  }

  // Process each successful GPS update.
  function handlePosition(position){
    const pos = { lat: position.coords.latitude, lng: position.coords.longitude };
    currentPosition = pos;
    renderLegendList();
    setLocationStatus('Location found');
    // Move the current-location marker and keep the map centered on the device.
    userMarker.setPosition(pos);
    map.panTo(pos);
    if(firstFix){
      map.setZoom(15);
      firstFix = false;
    }
  }

  // Convert browser geolocation errors into readable status messages.
  function handleError(err){
    const messages = {
      1: 'Location permission was denied. Allow it in your browser settings.',
      2: 'Your location could not be determined. Check the device location service.',
      3: 'Location request timed out. Try again.'
    };
    const message = err && messages[err.code]
      ? messages[err.code]
      : 'Unable to get your current location.';
    setLocationStatus(message);
    console.warn('Geolocation error or permission denied:', err.message || err);
  }

  // Request one fresh location fix, optionally continuing a pending route action.
  function requestCurrentLocation(onSuccess){
    if(!('geolocation' in navigator)){
      setLocationStatus('Location is not supported by this browser.');
      return;
    }
      if(!window.isSecureContext){
        setLocationStatus('Location requires HTTPS or http://localhost.');
        return;
      }
    setLocationStatus('Requesting location permission...');
    navigator.geolocation.getCurrentPosition(function(position){
      handlePosition(position);
      if(onSuccess) onSuccess();
    }, handleError, { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 });
  }

  // Let the user manually trigger permission and location lookup.
  // A direct user click requests permission and centers on the browser location.
  locateBtn && locateBtn.addEventListener('click', requestCurrentLocation);

  // Check permission and begin continuous tracking when permission already exists.
  if('geolocation' in navigator){
    navigator.permissions && navigator.permissions.query({ name: 'geolocation' }).then(function(permissionStatus){
      // If permission is already granted, start watching immediately. Otherwise, request it.
      if(permissionStatus.state === 'granted'){
        // Get an immediate fix and then keep the location current.
        requestCurrentLocation();
        navigator.geolocation.watchPosition(handlePosition, handleError, { enableHighAccuracy: true, maximumAge: 5000, timeout: 10000 });
        }else if(permissionStatus.state === 'denied'){
          setLocationStatus('Location is blocked. Allow it in the browser site settings, then try again.');
      } else {
        // Wait for the button because browsers may block automatic permission prompts.
        setLocationStatus('Click "Use my location" to allow location access.');
      }
    }).catch(function(){
      // Fallback if Permissions API is not supported
      setLocationStatus('Click "Use my location" to allow location access.');
    });
  } else {
    setLocationStatus('Location is not supported by this browser.');
    console.warn('Geolocation is not supported by this browser.');
  }
}

// Smooth scroll for in-page links
document.addEventListener('click', function(e){
  const target = e.target;
  if(target.tagName === 'A' && target.getAttribute('href') && target.getAttribute('href').startsWith('#')){
    e.preventDefault();
    const id = target.getAttribute('href').slice(1);
    const el = document.getElementById(id);
    if(el){
      el.scrollIntoView({behavior:'smooth',block:'start'});
    }
  }
});
