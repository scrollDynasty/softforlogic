// FreightPower Load Monitor - Content Script

// Селекторы для парсинга (обновленные для FreightPower)
const SELECTORS = {
  load_items: [
    // FreightPower специфичные селекторы для карточек грузов
    '.load-card',
    '.freight-card', 
    '.search-result-item',
    '[class*="load-result"]',
    '[class*="freight-result"]',
    // Общие селекторы для карточек
    '.card',
    '[class*="card"]',
    '.result-item',
    '[class*="result-item"]',
    // Контейнеры грузов
    'div[class*="load"]',
    'div[class*="freight"]',
    'article',
    'section[class*="load"]',
    // Таблицы и строки
    'tr[class*="load"]',
    'tbody tr',
    '.search-results tr',
    'table tbody tr',
    // Fallback селекторы
    'div:has(> *:contains("Power Only"))',
    'div:has(> *:contains("Dry Van"))',
    'div:has(> *:contains("Reefer"))',
    'div:has(> *:contains("Flatbed"))'
  ],
  
  // Селекторы для полей внутри карточек (FreightPower специфичные)
  load_id: [
    // Ищем числовые ID в начале карточки
    ':first-child:matches([0-9]+)',
    'span:matches([0-9]{10})',
    'div:matches([0-9]{10})',
    '*:contains("400")',
    // Общие селекторы
    '[data-testid="reference"]',
    '[class*="reference"]',
    '[class*="load-id"]',
    '[class*="id"]',
    '.reference',
    'td:first-child'
  ],
  
  capacity_type: [
    // FreightPower типы оборудования
    '*:contains("Power Only"):not(:contains("$")):not(:contains("mi"))',
    '*:contains("Dry Van"):not(:contains("$")):not(:contains("mi"))',
    '*:contains("Reefer"):not(:contains("$")):not(:contains("mi"))',
    '*:contains("Flatbed"):not(:contains("$")):not(:contains("mi"))',
    '*:contains("Step Deck"):not(:contains("$")):not(:contains("mi"))',
    '*:contains("Lowboy"):not(:contains("$")):not(:contains("mi"))',
    // Общие селекторы
    '[class*="capacity-type"]',
    '[class*="equipment-type"]',
    '[class*="trailer-type"]',
    '[class*="type"]'
  ],
  
  pickup_location: [
    // FreightPower специфичные селекторы для городов (все заглавные буквы)
    '*:matches([A-Z ]+, [A-Z]{2}):not(:contains("Deadhead"))',
    // Селекторы для элементов, содержащих города в верхнем регистре
    'div:contains(", OH")',
    'div:contains(", PA")', 
    'div:contains(", TX")',
    'div:contains(", CA")',
    'div:contains(", FL")',
    'span:contains(", OH")',
    'span:contains(", PA")',
    // Общие селекторы
    '[class*="origin"]',
    '[class*="pickup"]',
    '[class*="from"]',
    '[data-testid="pickup-location"]',
    '.origin, .pickup, .pickup-location'
  ],
  
  delivery_location: [
    // Аналогичные селекторы для места доставки
    '*:matches([A-Z ]+, [A-Z]{2}):not(:contains("Deadhead")):not(:first-of-type)',
    // Общие селекторы
    '[class*="destination"]',
    '[class*="delivery"]',
    '[class*="to"]',
    '[data-testid="delivery-location"]',
    '.destination, .delivery, .delivery-location'
  ],
  
  pickup_date: [
    // FreightPower даты в формате "Aug 21 12:02pm"
    '*:contains("Aug "):contains("pm")',
    '*:contains("Aug "):contains("am")',
    '*:matches(\\w{3} \\d{1,2} \\d{1,2}:\\d{2}[ap]m)',
    // Общие селекторы
    '[class*="pickup-date"]',
    '[class*="origin-date"]',
    '[class*="start-date"]'
  ],
  
  delivery_date: [
    // Аналогично для дат доставки
    '*:contains("Aug "):contains("pm"):not(:first-of-type)',
    '*:contains("Aug "):contains("am"):not(:first-of-type)',
    // Общие селекторы
    '[class*="delivery-date"]',
    '[class*="destination-date"]',
    '[class*="end-date"]'
  ],
  
  miles: [
    // FreightPower мили отображаются как "425 miles"
    '*:contains(" miles"):not(:contains("Deadhead"))',
    '*:matches(\\d+ miles)',
    // Общие селекторы
    '[class*="miles"]',
    '[class*="distance"]',
    '[data-testid="miles"]',
    '.distance, .total-miles'
  ],
  
  deadhead: [
    // FreightPower deadhead как "Deadhead 195 mi"
    '*:contains("Deadhead"):contains("mi")',
    '*:matches(Deadhead \\d+ mi)',
    // Общие селекторы
    '[class*="deadhead"]',
    '[class*="empty-miles"]',
    '.deadhead, .empty-miles'
  ],
  
  rate: [
    // FreightPower ставки как "$1,019"
    '*:contains("$"):not(:contains("lbs")):not(:contains("mi"))',
    '*:matches(\\$[0-9,]+)',
    // Общие селекторы
    '[class*="rate"]',
    '[class*="price"]',
    '[class*="pay"]',
    '.rate, .price, .pay, .freight-rate'
  ],
  
  weight: [
    // FreightPower вес как "44,500 lbs"
    '*:contains(" lbs")',
    '*:matches(\\d{1,3},?\\d{3} lbs)',
    '[class*="weight"]',
    '.weight'
  ]
};

// Состояние мониторинга
let monitoringState = {
  isActive: false,
  isLoggedIn: false,
  scanInterval: null,
  settings: null,
  foundLoads: new Map(), // Кеш найденных грузов для избежания дубликатов
  lastScanTime: 0,
  scanCount: 0,
  adaptiveInterval: 3000,
  pendingScan: false // Флаг для отслеживания ожидающих сканирований
};

// Инициализация при загрузке
(function initialize() {
  console.log('FreightPower Load Monitor content script loaded');
  
  // Проверяем авторизацию при загрузке
  checkLoginStatus();
  
  // Слушаем сообщения от background script
  chrome.runtime.onMessage.addListener(handleMessage);
  
  // Периодически проверяем авторизацию
  setInterval(checkLoginStatus, 5000);
  
  // Наблюдаем за изменениями DOM
  observePageChanges();
})();

// Детекция успешной авторизации (синхронизирована с background.js)
function detectLogin() {
  // Проверяем URL
  const isOnFreightPower = window.location.href.includes('freightpower.schneider.com');
  const notOnLoginPage = !window.location.href.includes('/login') && !window.location.href.includes('/signin');
  
  if (!isOnFreightPower || !notOnLoginPage) {
    return false;
  }
  
  // Проверяем наличие элементов авторизованного пользователя
  const authIndicators = [
    document.querySelector('[data-user-authenticated]'),
    document.querySelector('.dashboard'),
    document.querySelector('.user-menu'),
    document.querySelector('.header-user'),
    document.querySelector('[class*="user-nav"]'),
    document.querySelector('[class*="profile"]'),
    document.querySelector('nav[class*="user"]'),
    document.querySelector('[class*="logged-in"]'),
    document.querySelector('[class*="authenticated"]')
  ];
  
  const hasAuthElement = authIndicators.some(el => el !== null);
  
  // Проверяем storage и cookies
  const hasAuthStorage = localStorage.getItem('userToken') || 
                        sessionStorage.getItem('authToken') ||
                        localStorage.getItem('auth') ||
                        sessionStorage.getItem('auth');
  
  const hasAuthCookie = document.cookie.includes('auth') || 
                       document.cookie.includes('session') ||
                       document.cookie.includes('token');
  
  // Проверяем наличие основных элементов страницы поиска
  const hasSearchElements = document.querySelector('.search-results') ||
                          document.querySelector('[class*="search"]') ||
                          document.querySelector('[class*="load"]') ||
                          document.querySelector('main');
  
  // Считаем пользователя авторизованным, если выполнено несколько условий
  const isLoggedIn = isOnFreightPower && notOnLoginPage && 
                    (hasAuthElement || hasAuthStorage || hasAuthCookie || hasSearchElements);
  
  console.log('Login check:', {
    isOnFreightPower,
    notOnLoginPage,
    hasAuthElement,
    hasAuthStorage,
    hasAuthCookie,
    hasSearchElements,
    result: isLoggedIn
  });
  
  return isLoggedIn;
}

// Проверка статуса авторизации
function checkLoginStatus() {
  const wasLoggedIn = monitoringState.isLoggedIn;
  monitoringState.isLoggedIn = detectLogin();
  
  // Если статус изменился
  if (wasLoggedIn !== monitoringState.isLoggedIn) {
    if (monitoringState.isLoggedIn) {
      console.log('✅ User logged in to FreightPower');
      chrome.runtime.sendMessage({ 
        type: 'LOGIN_DETECTED',
        url: window.location.href
      }).catch(error => {
        console.error('Error sending login message:', error);
      });
    } else {
      console.log('🔒 User logged out from FreightPower');
      chrome.runtime.sendMessage({ type: 'LOGOUT_DETECTED' }).catch(error => {
        console.error('Error sending logout message:', error);
      });
      stopMonitoring();
    }
  }
}

// Обработка сообщений от background script
function handleMessage(message, sender, sendResponse) {
  console.log('Received message:', message.type);
  
  switch (message.type) {
    case 'START_MONITORING':
      if (!monitoringState.isActive && monitoringState.isLoggedIn) {
        startMonitoring(message.settings);
        sendResponse({ success: true });
      } else {
        sendResponse({ 
          success: false, 
          reason: monitoringState.isLoggedIn ? 'Already monitoring' : 'Not logged in' 
        });
      }
      break;
      
    case 'STOP_MONITORING':
      stopMonitoring();
      sendResponse({ success: true });
      break;
      
    case 'GET_STATUS':
      sendResponse({
        isActive: monitoringState.isActive,
        isLoggedIn: monitoringState.isLoggedIn,
        scanCount: monitoringState.scanCount,
        foundLoads: monitoringState.foundLoads.size
      });
      break;
      
    case 'PLAY_SOUND':
      playAlertSound();
      sendResponse({ success: true });
      break;
      
    case 'FORCE_SCAN':
      if (monitoringState.isActive) {
        scanForLoads();
        sendResponse({ success: true });
      } else {
        sendResponse({ success: false, reason: 'Monitoring not active' });
      }
      break;
      
    default:
      console.warn('Unknown message type:', message.type);
      sendResponse({ success: false, reason: 'Unknown message type' });
  }
  
  return true; // Указывает, что ответ может быть асинхронным
}

// Запуск мониторинга
function startMonitoring(settings) {
  if (monitoringState.isActive) {
    console.log('Monitoring already active');
    return;
  }
  
  if (!monitoringState.isLoggedIn) {
    console.log('Cannot start monitoring: not logged in');
    return;
  }
  
  monitoringState.settings = settings || {};
  monitoringState.isActive = true;
  monitoringState.scanCount = 0;
  monitoringState.foundLoads.clear();
  
  console.log('Starting automatic load monitoring...');
  
  // Запускаем первое сканирование сразу
  scanForLoads();
  
  // Устанавливаем интервал для регулярного сканирования
  monitoringState.scanInterval = setInterval(() => {
    scanForLoads();
  }, monitoringState.adaptiveInterval);
  
  // Показываем индикатор активности
  showMonitoringIndicator();
}

// Остановка мониторинга
function stopMonitoring() {
  if (!monitoringState.isActive) {
    return;
  }
  
  monitoringState.isActive = false;
  
  if (monitoringState.scanInterval) {
    clearInterval(monitoringState.scanInterval);
    monitoringState.scanInterval = null;
  }
  
  hideMonitoringIndicator();
  
  console.log('Load monitoring stopped');
}

// Перезапуск мониторинга с новыми настройками
function restartMonitoring() {
  if (monitoringState.isActive) {
    const settings = monitoringState.settings;
    stopMonitoring();
    setTimeout(() => startMonitoring(settings), 1000);
  }
}

// Основная функция сканирования грузов
function scanForLoads() {
  if (!monitoringState.isActive || !monitoringState.isLoggedIn) {
    return;
  }
  
  const startTime = Date.now();
  monitoringState.scanCount++;
  
  console.log(`Scanning for loads... (scan #${monitoringState.scanCount})`);
  
  try {
    const loadElements = findLoadElements();
    
    if (loadElements.length === 0) {
      console.log('No load elements found on page');
      adjustScanInterval('no_loads');
      return;
    }
    
    console.log(`Found ${loadElements.length} load elements`);
    
    let newLoadsFound = 0;
    let profitableLoadsFound = 0;
    
    loadElements.forEach((element, index) => {
      try {
        const loadData = parseLoadElement(element);
        
        if (loadData && loadData.id && !monitoringState.foundLoads.has(loadData.id)) {
          // Новый груз найден
          monitoringState.foundLoads.set(loadData.id, {
            ...loadData,
            foundAt: Date.now(),
            scanNumber: monitoringState.scanCount
          });
          
          newLoadsFound++;
          
          // Рассчитываем прибыльность
          const profitability = calculateProfitability(loadData);
          
          if (profitability.isProfitable && passesFilters(loadData, profitability)) {
            profitableLoadsFound++;
            
            // Отправляем найденный груз в background script
            chrome.runtime.sendMessage({
              type: 'LOAD_FOUND',
              data: {
                ...loadData,
                ...profitability,
                foundAt: Date.now(),
                scanNumber: monitoringState.scanCount
              }
            }).catch(error => {
              console.error('Error sending load found message:', error);
            });
            
            console.log(`💰 Profitable load found: ${loadData.id} - $${profitability.ratePerMile.toFixed(2)}/mile`);
          }
        }
      } catch (error) {
        console.error(`Error parsing load element ${index}:`, error);
      }
    });
    
    // Обновляем статистику
    chrome.runtime.sendMessage({
      type: 'UPDATE_STATISTICS',
      data: {
        totalScans: 1,
        loadsFound: newLoadsFound,
        profitableLoads: profitableLoadsFound,
        lastActive: Date.now()
      }
    }).catch(error => {
      console.error('Error updating statistics:', error);
    });
    
    // Адаптируем интервал сканирования
    if (newLoadsFound > 0) {
      adjustScanInterval('loads_found');
    } else {
      adjustScanInterval('no_new_loads');
    }
    
    const scanDuration = Date.now() - startTime;
    console.log(`Scan completed in ${scanDuration}ms. New loads: ${newLoadsFound}, Profitable: ${profitableLoadsFound}`);
    
  } catch (error) {
    console.error('Error during load scanning:', error);
    adjustScanInterval('error');
  }
  
  monitoringState.lastScanTime = Date.now();
}

// Поиск элементов грузов на странице
function findLoadElements() {
  console.log('🔍 Searching for load elements...');
  
  // Сначала пробуем найти контейнер с результатами поиска
  const searchContainers = [
    '.search-results',
    '[class*="search-result"]',
    '[class*="result-container"]',
    '[class*="load-list"]',
    '[class*="freight-list"]',
    'main [class*="container"]',
    '[role="main"]',
    '#app main',
    '.content-area'
  ];
  
  let container = document.body;
  for (const selector of searchContainers) {
    const found = document.querySelector(selector);
    if (found) {
      container = found;
      console.log(`📦 Found search container: ${selector}`);
      break;
    }
  }
  
  // Ищем элементы грузов
  for (const selector of SELECTORS.load_items) {
    const elements = container.querySelectorAll(selector);
    if (elements.length > 0) {
      console.log(`✅ Found ${elements.length} load elements using selector: ${selector}`);
      
      // Проверяем, что это действительно карточки грузов
      const validElements = Array.from(elements).filter(el => {
        // Элемент должен содержать хотя бы Origin или Destination
        const text = el.textContent || '';
        const hasLocation = text.includes('Origin') || text.includes('Destination') || 
                          text.includes(', ') || // Города обычно через запятую
                          /[A-Z]{2}\s*\d{5}/.test(text); // ZIP коды
        
        // Элемент должен быть достаточно большим (не пустым)
        const hasContent = el.childElementCount > 0 || text.length > 20;
        
        return hasLocation && hasContent;
      });
      
      if (validElements.length > 0) {
        console.log(`✅ Validated ${validElements.length} load elements`);
        return validElements;
      }
    }
  }
  
  // Если не нашли по селекторам, пробуем эвристический поиск
  console.log('⚠️ No elements found with selectors, trying heuristic search...');
  
  const allElements = container.querySelectorAll('div, article, section, tr');
  const potentialLoads = Array.from(allElements).filter(el => {
    const text = el.textContent || '';
    
    // Проверяем наличие ключевых слов
    const hasOrigin = text.includes('Origin') || /\b[A-Z][a-z]+(?:ville|ton|burg|city|town)\b/.test(text);
    const hasDestination = text.includes('Destination') || text.split(',').length > 2;
    const hasState = /\b[A-Z]{2}\b/.test(text);
    const hasMiles = /\b\d+\s*mi/i.test(text) || text.includes('miles');
    const hasDate = /\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}/i.test(text);
    
    // Элемент должен содержать несколько признаков груза
    const score = [hasOrigin, hasDestination, hasState, hasMiles, hasDate].filter(Boolean).length;
    
    return score >= 2 && el.childElementCount > 2;
  });
  
  if (potentialLoads.length > 0) {
    console.log(`🔍 Found ${potentialLoads.length} potential load elements through heuristic search`);
    return potentialLoads;
  }
  
  console.log('❌ No load elements found on page');
  return [];
}

// Парсинг данных груза из элемента (FreightPower специфичная логика)
function parseLoadElement(element) {
  const loadData = {
    id: null,
    capacityType: null,
    pickup: null,
    delivery: null,
    pickupCity: null,
    pickupState: null,
    pickupZip: null,
    deliveryCity: null,
    deliveryState: null,
    deliveryZip: null,
    pickupDate: null,
    deliveryDate: null,
    miles: 0,
    deadhead: 0,
    rate: 0,
    weight: 0,
    element: element
  };
  
  const fullText = element.textContent || '';
  console.log('🔍 Parsing FreightPower load element:', fullText.substring(0, 300));
  
  // Сначала пробуем FreightPower специфичное парсинг прямо из текста
  const freightPowerData = parseFreightPowerText(fullText);
  if (freightPowerData) {
    Object.assign(loadData, freightPowerData);
  }
  
  // Если не удалось через текстовое парсинг, используем селекторы
  if (!loadData.id) {
    loadData.id = extractText(element, SELECTORS.load_id) || generateLoadId(element);
  }
  
  if (!loadData.capacityType) {
    loadData.capacityType = extractText(element, SELECTORS.capacity_type);
  }
  
  // Извлекаем локации через селекторы если не нашли через текст
  if (!loadData.pickup || !loadData.delivery) {
    const pickupText = extractText(element, SELECTORS.pickup_location);
    if (pickupText) {
      loadData.pickup = pickupText;
      const pickupParsed = parseLocation(pickupText);
      loadData.pickupCity = pickupParsed.city;
      loadData.pickupState = pickupParsed.state;
      loadData.pickupZip = pickupParsed.zip;
    }
    
    const deliveryText = extractText(element, SELECTORS.delivery_location);
    if (deliveryText) {
      loadData.delivery = deliveryText;
      const deliveryParsed = parseLocation(deliveryText);
      loadData.deliveryCity = deliveryParsed.city;
      loadData.deliveryState = deliveryParsed.state;
      loadData.deliveryZip = deliveryParsed.zip;
    }
  }
  
  // Fallback: извлекаем локации из общего текста
  if (!loadData.pickup || !loadData.delivery) {
    const locationData = extractLocationsFromText(fullText);
    if (locationData.pickup && !loadData.pickup) {
      loadData.pickup = locationData.pickup;
      const pickupParsed = parseLocation(locationData.pickup);
      loadData.pickupCity = pickupParsed.city;
      loadData.pickupState = pickupParsed.state;
      loadData.pickupZip = pickupParsed.zip;
    }
    if (locationData.delivery && !loadData.delivery) {
      loadData.delivery = locationData.delivery;
      const deliveryParsed = parseLocation(locationData.delivery);
      loadData.deliveryCity = deliveryParsed.city;
      loadData.deliveryState = deliveryParsed.state;
      loadData.deliveryZip = deliveryParsed.zip;
    }
  }
  
  // Извлекаем остальные данные через селекторы если не нашли через текст
  if (!loadData.pickupDate) {
    loadData.pickupDate = extractText(element, SELECTORS.pickup_date);
  }
  
  if (!loadData.deliveryDate) {
    loadData.deliveryDate = extractText(element, SELECTORS.delivery_date);
  }
  
  if (!loadData.miles) {
    const milesText = extractText(element, SELECTORS.miles);
    loadData.miles = parseNumber(milesText);
  }
  
  if (!loadData.deadhead) {
    const deadheadText = extractText(element, SELECTORS.deadhead);
    loadData.deadhead = parseNumber(deadheadText);
  }
  
  if (!loadData.rate) {
    const rateText = extractText(element, SELECTORS.rate);
    loadData.rate = parseNumber(rateText);
  }
  
  if (!loadData.weight) {
    const weightText = extractText(element, SELECTORS.weight);
    loadData.weight = parseNumber(weightText);
  }
  
  // Валидация данных
  if (!loadData.pickup || !loadData.delivery) {
    console.warn('❌ Missing pickup or delivery location:', {
      pickup: loadData.pickup,
      delivery: loadData.delivery,
      elementText: fullText.substring(0, 200)
    });
    return null;
  }
  
  // Если нет ID, генерируем уникальный
  if (!loadData.id) {
    loadData.id = generateLoadId(loadData);
  }
  
  console.log('✅ Parsed FreightPower load:', {
    id: loadData.id,
    type: loadData.capacityType,
    pickup: `${loadData.pickupCity}, ${loadData.pickupState}`,
    delivery: `${loadData.deliveryCity}, ${loadData.deliveryState}`,
    miles: loadData.miles,
    deadhead: loadData.deadhead,
    rate: loadData.rate,
    weight: loadData.weight
  });
  
  return loadData;
}

// Специфичное парсинг FreightPower текста
function parseFreightPowerText(text) {
  const data = {};
  
  try {
    // Извлекаем ID груза (10-значное число в начале)
    const idMatch = text.match(/(\d{10})/);
    if (idMatch) {
      data.id = idMatch[1];
    }
    
    // Извлекаем тип оборудования
    const typeMatch = text.match(/(Power Only|Dry Van|Reefer|Flatbed|Step Deck|Lowboy)/);
    if (typeMatch) {
      data.capacityType = typeMatch[1];
    }
    
    // Извлекаем ставку
    const rateMatch = text.match(/\$([0-9,]+)/);
    if (rateMatch) {
      data.rate = parseNumber(rateMatch[0]);
    }
    
    // Извлекаем мили
    const milesMatch = text.match(/(\d+)\s+miles/);
    if (milesMatch) {
      data.miles = parseInt(milesMatch[1]);
    }
    
    // Извлекаем вес
    const weightMatch = text.match(/([0-9,]+)\s+lbs/);
    if (weightMatch) {
      data.weight = parseNumber(weightMatch[0]);
    }
    
    // Извлекаем deadhead
    const deadheadMatch = text.match(/Deadhead\s+(\d+)\s+mi/);
    if (deadheadMatch) {
      data.deadhead = parseInt(deadheadMatch[1]);
    }
    
    // Извлекаем локации (города в верхнем регистре)
    const locations = text.match(/([A-Z ]+,\s*[A-Z]{2})/g);
    if (locations && locations.length >= 2) {
      // Фильтруем, исключая локации рядом с "Deadhead"
      const validLocations = locations.filter(loc => {
        const locIndex = text.indexOf(loc);
        const contextBefore = text.substring(Math.max(0, locIndex - 20), locIndex);
        const contextAfter = text.substring(locIndex, locIndex + loc.length + 20);
        return !contextBefore.includes('Deadhead') && !contextAfter.includes('Deadhead');
      });
      
      if (validLocations.length >= 2) {
        data.pickup = validLocations[0].trim();
        data.delivery = validLocations[1].trim();
        
        // Парсим города и штаты
        const pickupParsed = parseLocation(data.pickup);
        data.pickupCity = pickupParsed.city;
        data.pickupState = pickupParsed.state;
        data.pickupZip = pickupParsed.zip;
        
        const deliveryParsed = parseLocation(data.delivery);
        data.deliveryCity = deliveryParsed.city;
        data.deliveryState = deliveryParsed.state;
        data.deliveryZip = deliveryParsed.zip;
      }
    }
    
    // Извлекаем даты
    const dateMatches = text.match(/(\w{3}\s+\d{1,2}\s+\d{1,2}:\d{2}[ap]m)/g);
    if (dateMatches && dateMatches.length >= 2) {
      data.pickupDate = dateMatches[0];
      data.deliveryDate = dateMatches[1];
    }
    
    console.log('📝 FreightPower text parsing result:', data);
    return data;
    
  } catch (error) {
    console.error('Error parsing FreightPower text:', error);
    return null;
  }
}

// Парсинг местоположения из текста
function parseLocation(locationText) {
  if (!locationText) {
    return { city: null, state: null, zip: null };
  }
  
  const location = {
    city: null,
    state: null,
    zip: null
  };
  
  // Очищаем текст от лишних символов
  const cleanText = locationText.trim().replace(/\s+/g, ' ');
  
  // Ищем ZIP код (5 цифр)
  const zipMatch = cleanText.match(/\b(\d{5})\b/);
  if (zipMatch) {
    location.zip = zipMatch[1];
  }
  
  // Ищем штат (2 заглавные буквы)
  const stateMatch = cleanText.match(/\b([A-Z]{2})\b/);
  if (stateMatch) {
    location.state = stateMatch[1];
  }
  
  // Извлекаем город (все что до штата или ZIP кода)
  let cityText = cleanText;
  
  // Убираем ZIP код
  if (location.zip) {
    cityText = cityText.replace(new RegExp(`\\b${location.zip}\\b`), '').trim();
  }
  
  // Убираем штат
  if (location.state) {
    cityText = cityText.replace(new RegExp(`\\b${location.state}\\b`), '').trim();
  }
  
  // Убираем лишние знаки препинания
  cityText = cityText.replace(/[,\-\s]+$/, '').replace(/^[,\-\s]+/, '').trim();
  
  if (cityText) {
    location.city = cityText;
  }
  
  return location;
}

// Извлечение локаций из общего текста элемента (FreightPower специфичная логика)
function extractLocationsFromText(text) {
  const locations = { pickup: null, delivery: null };
  
  if (!text) return locations;
  
  console.log('🔍 Extracting locations from text:', text.substring(0, 200));
  
  // FreightPower специфичные паттерны
  
  // Паттерн 1: Ищем города в верхнем регистре с штатами
  // Пример: "LIMA, OH" и "SHIPPENSBURG, PA"
  const upperCaseLocations = text.match(/([A-Z ]+,\s*[A-Z]{2})/g);
  
  if (upperCaseLocations && upperCaseLocations.length >= 2) {
    // Фильтруем локации, исключая те, что содержат "Deadhead"
    const validLocations = upperCaseLocations.filter(loc => 
      !text.substring(text.indexOf(loc) - 20, text.indexOf(loc) + 20).includes('Deadhead')
    );
    
    if (validLocations.length >= 2) {
      locations.pickup = validLocations[0].trim();
      locations.delivery = validLocations[1].trim();
      console.log('✅ Found locations via uppercase pattern:', locations);
      return locations;
    }
  }
  
  // Паттерн 2: Ищем по контексту с датами
  // В FreightPower локации идут перед датами
  const locationWithDatePattern = /([A-Z ]+,\s*[A-Z]{2})\s*\n\s*\w{3}\s+\d{1,2}/g;
  const locationsWithDates = [...text.matchAll(locationWithDatePattern)];
  
  if (locationsWithDates.length >= 2) {
    locations.pickup = locationsWithDates[0][1].trim();
    locations.delivery = locationsWithDates[1][1].trim();
    console.log('✅ Found locations via date context pattern:', locations);
    return locations;
  }
  
  // Паттерн 3: Ищем по ключевым словам
  const pickupKeywords = ['Drop Empty Trailer', 'Live Load'];
  const deliveryKeywords = ['Drop Loaded Trailer', 'Live Unload'];
  
  for (const keyword of pickupKeywords) {
    const keywordIndex = text.indexOf(keyword);
    if (keywordIndex > 0) {
      // Ищем локацию перед этим ключевым словом
      const beforeKeyword = text.substring(Math.max(0, keywordIndex - 100), keywordIndex);
      const locationMatch = beforeKeyword.match(/([A-Z ]+,\s*[A-Z]{2})/);
      if (locationMatch && !locations.pickup) {
        locations.pickup = locationMatch[1].trim();
      }
    }
  }
  
  for (const keyword of deliveryKeywords) {
    const keywordIndex = text.indexOf(keyword);
    if (keywordIndex > 0) {
      // Ищем локацию перед этим ключевым словом
      const beforeKeyword = text.substring(Math.max(0, keywordIndex - 100), keywordIndex);
      const locationMatch = beforeKeyword.match(/([A-Z ]+,\s*[A-Z]{2})/);
      if (locationMatch && !locations.delivery && locationMatch[1] !== locations.pickup) {
        locations.delivery = locationMatch[1].trim();
      }
    }
  }
  
  // Паттерн 4: Fallback - все локации в порядке появления
  if (!locations.pickup || !locations.delivery) {
    const allLocations = text.match(/([A-Z ]+,\s*[A-Z]{2})/g);
    if (allLocations && allLocations.length >= 2) {
      // Убираем дубликаты и берем первые две уникальные
      const uniqueLocations = [...new Set(allLocations)];
      if (uniqueLocations.length >= 2) {
        if (!locations.pickup) locations.pickup = uniqueLocations[0].trim();
        if (!locations.delivery) locations.delivery = uniqueLocations[1].trim();
      }
    }
  }
  
  console.log('🎯 Final extracted locations:', locations);
  return locations;
}

// Генерация уникального ID для груза
function generateLoadId(data) {
  if (data.pickup && data.delivery) {
    return `${data.pickup}-${data.delivery}-${Date.now()}`.replace(/\s+/g, '-');
  }
  return `load-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

// Извлечение радиуса из элемента
function extractRadius(element) {
  if (!element) return null;
  
  const text = element.textContent || element.value || '';
  const match = text.match(/(\d+)\s*mi/i);
  return match ? parseInt(match[1]) : null;
}

// Извлечение текста из элемента по селекторам (FreightPower специфичная логика)
function extractText(parentElement, selectors) {
  const fullText = parentElement.textContent || '';
  
  for (const selector of selectors) {
    try {
      let elements = [];
      
      // Обработка специальных селекторов с :contains()
      if (selector.includes(':contains(')) {
        const match = selector.match(/\*:contains\("([^"]+)"\)(.*)$/);
        if (match) {
          const searchText = match[1];
          const modifier = match[2];
          
          // Ищем все элементы, содержащие искомый текст
          const allElements = parentElement.querySelectorAll('*');
          for (const el of allElements) {
            if (el.textContent && el.textContent.includes(searchText)) {
              // Применяем модификаторы
              if (modifier.includes(':not(:contains("$"))')) {
                if (el.textContent.includes('$')) continue;
              }
              if (modifier.includes(':not(:contains("mi"))')) {
                if (el.textContent.includes('mi')) continue;
              }
              if (modifier.includes(':not(:contains("lbs"))')) {
                if (el.textContent.includes('lbs')) continue;
              }
              if (modifier.includes(':not(:contains("Deadhead"))')) {
                if (el.textContent.includes('Deadhead')) continue;
              }
              if (modifier.includes(':not(:first-of-type)')) {
                // Пропускаем первое вхождение
                const sameTextElements = Array.from(allElements).filter(e => 
                  e.textContent && e.textContent.includes(searchText)
                );
                if (sameTextElements[0] === el) continue;
              }
              
              elements.push(el);
            }
          }
        }
      }
      // Обработка :matches() селекторов с регулярными выражениями
      else if (selector.includes(':matches(')) {
        const match = selector.match(/\*:matches\(([^)]+)\)/);
        if (match) {
          const regexPattern = match[1];
          const regex = new RegExp(regexPattern, 'g');
          
          // Ищем совпадения в тексте
          const matches = fullText.match(regex);
          if (matches && matches.length > 0) {
            // Возвращаем первое совпадение
            return matches[0];
          }
        }
      }
      // Обычные селекторы
      else {
        try {
          elements = Array.from(parentElement.querySelectorAll(selector));
        } catch (selectorError) {
          // Некоторые селекторы могут не работать в браузере
          console.debug(`Selector "${selector}" not supported:`, selectorError.message);
          continue;
        }
      }
      
      // Проверяем найденные элементы
      for (const el of elements) {
        const text = extractTextFromElement(el);
        if (text) {
          return text;
        }
      }
    } catch (e) {
      console.debug(`Selector error for "${selector}":`, e.message);
    }
  }
  
  return null;
}

// Извлечение текста из конкретного элемента
function extractTextFromElement(element) {
  if (!element) return null;
  
  // Для input/select элементов берем value
  if (element.tagName === 'INPUT' || element.tagName === 'SELECT') {
    return element.value || null;
  }
  
  // Для элементов с одним текстовым узлом
  if (element.childNodes.length === 1 && element.childNodes[0].nodeType === Node.TEXT_NODE) {
    const text = element.textContent.trim();
    return text || null;
  }
  
  // Для сложных элементов ищем текст, исключая вложенные labels
  const clonedElement = element.cloneNode(true);
  const labels = clonedElement.querySelectorAll('label');
  labels.forEach(label => label.remove());
  
  const text = clonedElement.textContent.trim();
  return text || null;
}

// Парсинг числовых значений
function parseNumber(text) {
  if (!text) return 0;
  
  // Убираем все символы кроме цифр, точек и запятых
  const cleaned = text.replace(/[^\d\.,]/g, '');
  
  // Конвертируем в число
  const number = parseFloat(cleaned.replace(/,/g, ''));
  
  return isNaN(number) ? 0 : number;
}

// Расчет прибыльности груза
function calculateProfitability(load) {
  const totalMiles = load.miles + load.deadhead;
  const ratePerMile = totalMiles > 0 ? load.rate / totalMiles : 0;
  const deadheadRatio = load.miles > 0 ? load.deadhead / load.miles : 1;
  
  // Коэффициент прибыльности (учитывает deadhead)
  const profitabilityScore = ratePerMile * (1 - deadheadRatio * 0.3);
  
  // Определяем приоритет
  let priority = 'LOW';
  if (profitabilityScore > 3.5) {
    priority = 'HIGH';
  } else if (profitabilityScore > 2.5) {
    priority = 'MEDIUM';
  }
  
  return {
    ratePerMile,
    profitabilityScore,
    deadheadRatio,
    isProfitable: ratePerMile >= 2.50 && deadheadRatio <= 0.25,
    priority
  };
}

// Проверка фильтров
function passesFilters(load, profitability) {
  const settings = monitoringState.settings || {};
  
  // Минимальная ставка за милю
  if (profitability.ratePerMile < (settings.minRatePerMile || 2.50)) {
    return false;
  }
  
  // Максимальный deadhead
  if (load.deadhead > (settings.maxDeadhead || 50)) {
    return false;
  }
  
  // Минимальное расстояние
  if (load.miles < (settings.minDistance || 200)) {
    return false;
  }
  
  // Максимальное расстояние (если указано)
  if (settings.maxDistance && load.miles > settings.maxDistance) {
    return false;
  }
  
  // Фильтр по регионам (если указаны)
  if (settings.regions && settings.regions.length > 0) {
    const matchesRegion = settings.regions.some(region => 
      (load.pickupState && load.pickupState.toLowerCase().includes(region.toLowerCase())) ||
      (load.deliveryState && load.deliveryState.toLowerCase().includes(region.toLowerCase())) ||
      (load.pickup && load.pickup.toLowerCase().includes(region.toLowerCase())) ||
      (load.delivery && load.delivery.toLowerCase().includes(region.toLowerCase()))
    );
    if (!matchesRegion) {
      return false;
    }
  }
  
  return true;
}

// Адаптивная настройка интервала сканирования
function adjustScanInterval(result) {
  const currentInterval = monitoringState.adaptiveInterval;
  
  switch (result) {
    case 'loads_found':
      // Найдены новые грузы - ускоряем сканирование
      monitoringState.adaptiveInterval = Math.max(2000, currentInterval - 500);
      break;
      
    case 'no_new_loads':
      // Новых грузов нет - замедляем сканирование
      monitoringState.adaptiveInterval = Math.min(5000, currentInterval + 200);
      break;
      
    case 'no_loads':
      // Грузов вообще нет на странице - значительно замедляем
      monitoringState.adaptiveInterval = Math.min(10000, currentInterval + 1000);
      break;
      
    case 'error':
      // Ошибка - замедляем сканирование
      monitoringState.adaptiveInterval = Math.min(8000, currentInterval + 1000);
      break;
  }
  
  // Перезапускаем интервал с новой частотой
  if (monitoringState.scanInterval && monitoringState.adaptiveInterval !== currentInterval) {
    clearInterval(monitoringState.scanInterval);
    monitoringState.scanInterval = setInterval(() => {
      scanForLoads();
    }, monitoringState.adaptiveInterval);
    
    console.log(`Scan interval adjusted to ${monitoringState.adaptiveInterval}ms`);
  }
}

// Показ индикатора мониторинга
function showMonitoringIndicator() {
  // Убираем старый индикатор если есть
  hideMonitoringIndicator();
  
  const indicator = document.createElement('div');
  indicator.id = 'freightpower-monitor-indicator';
  indicator.innerHTML = `
    <div style="
      position: fixed;
      top: 10px;
      right: 10px;
      background: #4CAF50;
      color: white;
      padding: 8px 12px;
      border-radius: 4px;
      font-size: 12px;
      font-family: Arial, sans-serif;
      z-index: 10000;
      box-shadow: 0 2px 8px rgba(0,0,0,0.2);
      animation: pulse 2s infinite;
    ">
      🔍 Мониторинг активен
      <div style="font-size: 10px; opacity: 0.8;">
        Сканирований: <span id="scan-counter">0</span>
      </div>
    </div>
    <style>
      @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.7; }
        100% { opacity: 1; }
      }
    </style>
  `;
  
  document.body.appendChild(indicator);
  
  // Обновляем счетчик сканирований
  setInterval(() => {
    const counter = document.getElementById('scan-counter');
    if (counter && monitoringState.isActive) {
      counter.textContent = monitoringState.scanCount;
    }
  }, 1000);
}

// Скрытие индикатора мониторинга
function hideMonitoringIndicator() {
  const indicator = document.getElementById('freightpower-monitor-indicator');
  if (indicator) {
    indicator.remove();
  }
}

// Воспроизведение звукового сигнала
function playAlertSound() {
  try {
    // Создаем audio элемент для воспроизведения звука
    const audio = new Audio(chrome.runtime.getURL('sounds/alert.mp3'));
    audio.volume = 0.7;
    
    audio.play().then(() => {
      console.log('🔊 Alert sound played');
    }).catch(error => {
      console.error('Error playing sound:', error);
      
      // Fallback: используем Web Audio API
      try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        oscillator.frequency.value = 800; // Частота звука
        gainNode.gain.value = 0.3; // Громкость
        
        oscillator.start();
        oscillator.stop(audioContext.currentTime + 0.2); // Длительность 200мс
        
        console.log('🔊 Fallback beep played');
      } catch (fallbackError) {
        console.error('Fallback sound also failed:', fallbackError);
      }
    });
  } catch (error) {
    console.error('Failed to create audio element:', error);
  }
}

// Наблюдение за изменениями страницы
function observePageChanges() {
  console.log('👁️ Starting DOM observer...');
  
  // Отслеживаем изменения URL (для SPA)
  let lastUrl = location.href;
  new MutationObserver(() => {
    const url = location.href;
    if (url !== lastUrl) {
      lastUrl = url;
      console.log('📍 URL changed:', url);
      
      // Проверяем, находимся ли мы на странице поиска
      if (url.includes('/search') || url.includes('/app/search')) {
        console.log('🔍 On search page, checking for results...');
        setTimeout(() => {
          if (monitoringState.isActive) {
            scanForLoads();
          }
        }, 1000);
      }
    }
  }).observe(document, {subtree: true, childList: true});
  
  // Создаем основной наблюдатель за DOM
  const observer = new MutationObserver((mutations) => {
    // Проверяем, были ли добавлены новые элементы
    let hasNewContent = false;
    
    for (const mutation of mutations) {
      if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
        // Проверяем, содержат ли новые узлы потенциальные грузы
        for (const node of mutation.addedNodes) {
          if (node.nodeType === Node.ELEMENT_NODE) {
            const text = node.textContent || '';
            // Ищем признаки грузов
            if (text.includes('Origin') || text.includes('Destination') || 
                text.includes('miles') || /\$\d+/.test(text) ||
                node.querySelector && node.querySelector('[class*="load"], [class*="freight"], [class*="card"]')) {
              hasNewContent = true;
              break;
            }
          }
        }
      }
      
      if (hasNewContent) break;
    }
    
    // Если обнаружен новый контент и мониторинг активен
    if (hasNewContent && monitoringState.isActive && !monitoringState.pendingScan) {
      console.log('🆕 New content detected, scheduling scan...');
      
      // Устанавливаем флаг, чтобы избежать множественных сканирований
      monitoringState.pendingScan = true;
      
      // Ждем немного, чтобы страница полностью обновилась
      setTimeout(() => {
        monitoringState.pendingScan = false;
        if (monitoringState.isActive) {
          scanForLoads();
        }
      }, 500);
    }
  });
  
  // Конфигурация наблюдателя
  const config = {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['class', 'style'] // Отслеживаем изменения классов и стилей
  };
  
  // Запускаем наблюдение за всем документом
  observer.observe(document.body, config);
  
  // Также наблюдаем за конкретными контейнерами, если они есть
  const containers = [
    document.querySelector('.search-results'),
    document.querySelector('[class*="result-container"]'),
    document.querySelector('main'),
    document.querySelector('#app')
  ].filter(Boolean);
  
  containers.forEach(container => {
    console.log('👁️ Observing container:', container.className || container.tagName);
    observer.observe(container, config);
  });
  
  console.log('✅ DOM observer started');
}

// Очистка старых записей из кеша (каждые 30 минут)
setInterval(() => {
  const now = Date.now();
  const maxAge = 30 * 60 * 1000; // 30 минут
  
  for (const [loadId, loadData] of monitoringState.foundLoads.entries()) {
    if (now - loadData.foundAt > maxAge) {
      monitoringState.foundLoads.delete(loadId);
    }
  }
  
  console.log(`Cache cleaned. Remaining loads: ${monitoringState.foundLoads.size}`);
}, 30 * 60 * 1000);

// Диагностическая функция для анализа страницы
function diagnosePage() {
  console.log('🔍 Starting page diagnostics...');
  
  // Анализируем URL
  console.log('📍 Current URL:', window.location.href);
  console.log('📄 Page title:', document.title);
  
  // Проверяем основные контейнеры
  const containers = {
    'search-results': document.querySelector('.search-results'),
    'load-list': document.querySelector('[class*="load-list"]'),
    'freight-list': document.querySelector('[class*="freight-list"]'),
    'main': document.querySelector('main'),
    'app': document.querySelector('#app')
  };
  
  console.log('📦 Found containers:');
  for (const [name, element] of Object.entries(containers)) {
    if (element) {
      console.log(`  ✅ ${name}: ${element.tagName}.${element.className}`);
    } else {
      console.log(`  ❌ ${name}: not found`);
    }
  }
  
  // Проверяем элементы грузов
  const loadElements = findLoadElements();
  console.log(`🚛 Found ${loadElements.length} load elements`);
  
  if (loadElements.length > 0) {
    console.log('📝 Sample load element analysis:');
    const sample = loadElements[0];
    const parsed = parseLoadElement(sample);
    console.log('  Parsed data:', parsed);
    console.log('  Element HTML:', sample.outerHTML.substring(0, 500) + '...');
  }
  
  return {
    url: window.location.href,
    title: document.title,
    containers: Object.fromEntries(
      Object.entries(containers).map(([k, v]) => [k, !!v])
    ),
    loadElementsCount: loadElements.length,
    isLoggedIn: monitoringState.isLoggedIn
  };
}

// Экспорт функций для отладки (доступны в консоли)
window.freightPowerDebug = {
  diagnosePage,
  scanForLoads,
  findLoadElements,
  parseLoadElement,
  getState: () => monitoringState
};