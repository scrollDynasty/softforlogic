// FreightPower Load Monitor - Content Script

// Селекторы для парсинга (обновленные для FreightPower)
const SELECTORS = {
  load_items: [
    // Карточки грузов
    '[class*="card"][class*="load"]',
    '[class*="load-card"]',
    '[class*="freight-card"]',
    '[class*="search-result-card"]',
    '[class*="result-item"]',
    'div[class*="load"][class*="item"]',
    'article[class*="load"]',
    '.card',
    // Таблицы с грузами
    '[data-testid="load-row"]',
    '.load-item, .freight-item',
    'tr[class*="load"], tbody tr',
    '.search-results tr',
    '[class*="row"][class*="load"]',
    'table tbody tr'
  ],
  // Селекторы для полей внутри карточек
  load_id: [
    '[data-testid="reference"]',
    '[class*="reference-number"]',
    '[class*="load-number"]',
    '[class*="load-id"]',
    '.reference',
    '.load-reference, .id-column',
    'td:first-child',
    '[class*="id"]',
    '[class*="reference"]'
  ],
  capacity_type: [
    '[class*="capacity-type"]',
    '[class*="equipment-type"]',
    'label:contains("Capacity Type") ~ *',
    '*:contains("Capacity Type") + *',
    '[class*="type"]'
  ],
  pickup_location: [
    '[class*="origin"]',
    '[class*="pickup"]',
    'label:contains("Origin") ~ *',
    '*:contains("Origin") + *',
    '[data-testid="pickup-location"]',
    '.origin, .pickup, .pickup-location',
    'td:nth-child(2)'
  ],
  delivery_location: [
    '[class*="destination"]',
    '[class*="delivery"]',
    'label:contains("Destination") ~ *',
    '*:contains("Destination") + *',
    '[data-testid="delivery-location"]',
    '.destination, .delivery, .delivery-location',
    'td:nth-child(3)'
  ],
  pickup_date: [
    '[class*="pickup-date"]',
    '[class*="origin-date"]',
    'label:contains("Origin") ~ * [class*="date"]',
    '[class*="start-date"]'
  ],
  delivery_date: [
    '[class*="delivery-date"]',
    '[class*="destination-date"]',
    'label:contains("Destination") ~ * [class*="date"]',
    '[class*="end-date"]'
  ],
  miles: [
    '[class*="miles"]',
    '[class*="distance"]',
    'label:contains("Miles") ~ *',
    '*:contains("Miles") + *',
    '[data-testid="miles"]',
    '.distance, .total-miles, .miles-column',
    'td:nth-child(4)'
  ],
  deadhead: [
    '[class*="deadhead"]',
    '[class*="empty-miles"]',
    'label:contains("Deadhead") ~ *',
    '[data-testid="deadhead"]',
    '.deadhead, .empty-miles',
    'td:nth-child(5)'
  ],
  rate: [
    '[class*="rate"]',
    '[class*="price"]',
    '[class*="pay"]',
    'label:contains("Rate") ~ *',
    '*:contains("$")',
    '[data-testid="rate"]',
    '.rate, .price, .pay, .freight-rate',
    'td:nth-child(6)'
  ],
  radius: [
    '[class*="radius"]',
    '*:contains("mi")',
    'select[class*="radius"]',
    'input[type="range"]'
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
  pendingScan: false, // Флаг для отслеживания ожидающих сканирований
  scanTimeout: null, // Таймаут для сканирования
  watchdogInterval: null // Интервал для watchdog
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

// Детекция успешной авторизации (улучшенная версия)
function detectLogin() {
  // Проверяем URL
  const isOnFreightPower = window.location.href.includes('freightpower.schneider.com');
  const notOnLoginPage = !window.location.href.includes('/login') && 
                        !window.location.href.includes('/signin') && 
                        !window.location.href.includes('/auth');
  
  if (!isOnFreightPower) {
    return false;
  }
  
  // Если на странице логина - точно не авторизован
  if (!notOnLoginPage) {
    return false;
  }
  
  // Расширенная проверка элементов авторизованного пользователя
  const authIndicators = [
    // Специфичные для FreightPower
    document.querySelector('[data-user-authenticated]'),
    document.querySelector('[data-user-id]'),
    document.querySelector('[class*="user-profile"]'),
    document.querySelector('[class*="account-menu"]'),
    document.querySelector('.user-avatar'),
    document.querySelector('.profile-dropdown'),
    
    // Общие элементы
    document.querySelector('.dashboard'),
    document.querySelector('.user-menu'),
    document.querySelector('.header-user'),
    document.querySelector('[class*="user-nav"]'),
    document.querySelector('[class*="profile"]'),
    document.querySelector('nav[class*="user"]'),
    document.querySelector('[class*="logged-in"]'),
    document.querySelector('[class*="authenticated"]'),
    
    // Элементы навигации
    document.querySelector('nav'),
    document.querySelector('[role="navigation"]'),
    document.querySelector('.navbar'),
    document.querySelector('.header-nav')
  ];
  
  const hasAuthElement = authIndicators.some(el => el !== null);
  
  // Расширенная проверка storage и cookies
  const authStorageKeys = [
    'userToken', 'authToken', 'auth', 'accessToken', 'jwt',
    'session', 'user', 'userData', 'schneider_auth', 
    'freightpower_auth', 'auth_token', 'bearer_token'
  ];
  
  const hasAuthStorage = authStorageKeys.some(key => 
    localStorage.getItem(key) || sessionStorage.getItem(key)
  );
  
  const authCookiePatterns = [
    'auth', 'session', 'token', 'jwt', 'bearer',
    'schneider', 'freightpower', 'user', 'login'
  ];
  
  const hasAuthCookie = authCookiePatterns.some(pattern => 
    document.cookie.toLowerCase().includes(pattern)
  );
  
  // Проверяем наличие основных элементов приложения
  const appIndicators = [
    document.querySelector('.search-results'),
    document.querySelector('[class*="search"]'),
    document.querySelector('[class*="load"]'),
    document.querySelector('[class*="freight"]'),
    document.querySelector('main'),
    document.querySelector('[role="main"]'),
    document.querySelector('.content'),
    document.querySelector('#app'),
    document.querySelector('#root')
  ];
  
  const hasSearchElements = appIndicators.some(el => el !== null);
  
  // Проверяем отсутствие элементов страницы входа
  const loginElements = [
    document.querySelector('input[type="password"]'),
    document.querySelector('.login-form'),
    document.querySelector('[class*="signin"]'),
    document.querySelector('[class*="login"]'),
    document.querySelector('button[type="submit"]')
  ];
  
  const hasLoginElements = loginElements.some(el => el !== null);
  
  // Проверяем заголовок страницы
  const titleIndicatesLogin = document.title.toLowerCase().includes('login') ||
                             document.title.toLowerCase().includes('sign in') ||
                             document.title.toLowerCase().includes('authenticate');
  
  // Комплексная логика определения авторизации
  let isLoggedIn = false;
  
  if (isOnFreightPower && notOnLoginPage) {
    // Если есть явные признаки авторизации
    if (hasAuthElement || hasAuthStorage) {
      isLoggedIn = true;
    }
    // Если есть элементы приложения и нет элементов входа
    else if (hasSearchElements && !hasLoginElements && !titleIndicatesLogin) {
      isLoggedIn = true;
    }
    // Если есть куки авторизации и нет признаков страницы входа
    else if (hasAuthCookie && !hasLoginElements && !titleIndicatesLogin) {
      isLoggedIn = true;
    }
  }
  
  console.log('Enhanced login check:', {
    isOnFreightPower,
    notOnLoginPage,
    hasAuthElement,
    hasAuthStorage,
    hasAuthCookie,
    hasSearchElements,
    hasLoginElements,
    titleIndicatesLogin,
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
      
    case 'UPDATE_SETTINGS':
      if (message.settings) {
        console.log('Updating monitoring settings:', message.settings);
        monitoringState.settings = message.settings;
        
        // Обновляем адаптивный интервал если он изменился
        if (message.settings.scanInterval && message.settings.scanInterval !== monitoringState.adaptiveInterval) {
          monitoringState.adaptiveInterval = message.settings.scanInterval;
        }
        
        // Если мониторинг активен, перезапускаем с новыми настройками
        if (monitoringState.isActive) {
          restartMonitoring(message.settings);
        }
        
        sendResponse({ success: true });
      } else {
        sendResponse({ success: false, reason: 'No settings provided' });
      }
      break;
      
    default:
      console.warn('Unknown message type:', message.type);
      sendResponse({ success: false, reason: 'Unknown message type' });
  }
  
  return true; // Указывает, что ответ может быть асинхронным
}

// Запуск мониторинга (улучшенная версия)
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
  monitoringState.lastScanTime = Date.now();
  monitoringState.pendingScan = false;
  
  console.log('Starting automatic load monitoring with settings:', monitoringState.settings);
  
  // Запускаем первое сканирование сразу
  scheduleNextScan(0);
  
  // Показываем индикатор активности
  showMonitoringIndicator();
  
  // Устанавливаем watchdog для автоматического восстановления
  startMonitoringWatchdog();
}

// Остановка мониторинга (улучшенная версия)
function stopMonitoring() {
  if (!monitoringState.isActive) {
    return;
  }
  
  monitoringState.isActive = false;
  monitoringState.pendingScan = false;
  
  if (monitoringState.scanInterval) {
    clearInterval(monitoringState.scanInterval);
    monitoringState.scanInterval = null;
  }
  
  if (monitoringState.scanTimeout) {
    clearTimeout(monitoringState.scanTimeout);
    monitoringState.scanTimeout = null;
  }
  
  if (monitoringState.watchdogInterval) {
    clearInterval(monitoringState.watchdogInterval);
    monitoringState.watchdogInterval = null;
  }
  
  hideMonitoringIndicator();
  
  console.log('Load monitoring stopped');
}

// Планирование следующего сканирования
function scheduleNextScan(delay) {
  if (!monitoringState.isActive) return;
  
  if (monitoringState.scanTimeout) {
    clearTimeout(monitoringState.scanTimeout);
  }
  
  const actualDelay = delay || monitoringState.adaptiveInterval;
  
  monitoringState.scanTimeout = setTimeout(() => {
    if (monitoringState.isActive && monitoringState.isLoggedIn && !monitoringState.pendingScan) {
      performScan();
    }
  }, actualDelay);
}

// Выполнение сканирования с защитой от зависания
function performScan() {
  if (!monitoringState.isActive || !monitoringState.isLoggedIn || monitoringState.pendingScan) {
    return;
  }
  
  monitoringState.pendingScan = true;
  monitoringState.lastScanTime = Date.now();
  
  // Устанавливаем таймаут для предотвращения зависания
  const scanTimeout = setTimeout(() => {
    if (monitoringState.pendingScan) {
      console.warn('Scan timeout, resetting pending state');
      monitoringState.pendingScan = false;
      scheduleNextScan();
    }
  }, 30000); // 30 секунд максимум на сканирование
  
  try {
    scanForLoads();
  } catch (error) {
    console.error('Error during scan:', error);
  } finally {
    clearTimeout(scanTimeout);
    monitoringState.pendingScan = false;
    
    // Планируем следующее сканирование
    if (monitoringState.isActive) {
      scheduleNextScan();
    }
  }
}

// Watchdog для мониторинга состояния
function startMonitoringWatchdog() {
  if (monitoringState.watchdogInterval) {
    clearInterval(monitoringState.watchdogInterval);
  }
  
  monitoringState.watchdogInterval = setInterval(() => {
    if (!monitoringState.isActive) return;
    
    const now = Date.now();
    const timeSinceLastScan = now - monitoringState.lastScanTime;
    const maxIdleTime = monitoringState.adaptiveInterval * 3; // 3 интервала максимум
    
    // Проверяем, не зависло ли сканирование
    if (timeSinceLastScan > maxIdleTime) {
      console.warn('Monitoring appears to be stuck, restarting...');
      restartMonitoring();
      return;
    }
    
    // Проверяем, что пользователь еще авторизован
    if (!monitoringState.isLoggedIn) {
      console.log('User is no longer logged in, stopping monitoring');
      stopMonitoring();
      return;
    }
    
    // Проверяем доступность страницы
    if (document.hidden || !document.hasFocus()) {
      console.log('Page is hidden or not focused, reducing scan frequency');
      monitoringState.adaptiveInterval = Math.min(monitoringState.adaptiveInterval * 1.5, 15000);
    } else {
      // Восстанавливаем нормальную частоту если страница активна
      const normalInterval = monitoringState.settings?.scanInterval || 3000;
      if (monitoringState.adaptiveInterval > normalInterval) {
        monitoringState.adaptiveInterval = Math.max(monitoringState.adaptiveInterval * 0.8, normalInterval);
      }
    }
    
  }, 15000); // Проверяем каждые 15 секунд
}

// Перезапуск мониторинга с новыми настройками (улучшенная версия)
function restartMonitoring(newSettings) {
  if (monitoringState.isActive) {
    const settings = newSettings || monitoringState.settings;
    console.log('Restarting monitoring with settings:', settings);
    
    stopMonitoring();
    
    // Небольшая задержка перед перезапуском
    setTimeout(() => {
      if (monitoringState.isLoggedIn) {
        startMonitoring(settings);
      }
    }, 2000);
  }
}

// Основная функция сканирования грузов (оптимизированная версия)
function scanForLoads() {
  if (!monitoringState.isActive || !monitoringState.isLoggedIn) {
    return;
  }
  
  const startTime = Date.now();
  monitoringState.scanCount++;
  
  console.log(`Scanning for loads... (scan #${monitoringState.scanCount})`);
  
  try {
    // Очищаем старые записи из кеша для предотвращения утечек памяти
    cleanupFoundLoadsCache();
    
    const loadElements = findLoadElements();
    
    if (loadElements.length === 0) {
      console.log('No load elements found on page');
      adjustScanInterval('no_loads');
      return;
    }
    
    console.log(`Found ${loadElements.length} load elements`);
    
    let newLoadsFound = 0;
    let profitableLoadsFound = 0;
    const batchSize = 10; // Обрабатываем по 10 элементов за раз
    
    // Обрабатываем элементы батчами для лучшей производительности
    for (let i = 0; i < loadElements.length; i += batchSize) {
      const batch = loadElements.slice(i, i + batchSize);
      
      batch.forEach((element, batchIndex) => {
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
              
              const enrichedLoadData = {
                ...loadData,
                ...profitability,
                priority: calculatePriority(loadData, profitability),
                foundAt: Date.now()
              };
              
              // Отправляем в background script асинхронно
              chrome.runtime.sendMessage({
                type: 'LOAD_FOUND',
                data: enrichedLoadData
              }).catch(error => {
                console.error('Error sending load data:', error);
              });
              
              console.log('💰 Profitable load found:', enrichedLoadData);
            }
          }
          
        } catch (parseError) {
          console.warn(`Error parsing load element ${i + batchIndex}:`, parseError);
        }
      });
      
      // Небольшая пауза между батчами для предотвращения блокировки UI
      if (i + batchSize < loadElements.length) {
        // Используем Promise для асинхронной обработки
        setTimeout(() => {}, 0);
      }
    }
    
    const endTime = Date.now();
    const scanDuration = endTime - startTime;
    
    console.log(`Scan completed: ${newLoadsFound} new loads, ${profitableLoadsFound} profitable (${scanDuration}ms)`);
    
    // Адаптируем интервал на основе результатов
    if (profitableLoadsFound > 0) {
      adjustScanInterval('profitable_found');
    } else if (newLoadsFound > 0) {
      adjustScanInterval('loads_found');
    } else {
      adjustScanInterval('no_new_loads');
    }
    
    // Предупреждение о медленном сканировании
    if (scanDuration > 5000) {
      console.warn(`Slow scan detected: ${scanDuration}ms`);
      adjustScanInterval('slow_scan');
    }
    
    // Обновляем статистику асинхронно
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
    
  } catch (error) {
    console.error('Error during load scanning:', error);
    adjustScanInterval('error');
  }
}

// Очистка кеша найденных грузов
function cleanupFoundLoadsCache() {
  if (monitoringState.foundLoads.size <= 100) {
    return; // Кеш еще небольой
  }
  
  const now = Date.now();
  const maxAge = 30 * 60 * 1000; // 30 минут
  const maxSize = 50; // Максимальный размер кеша
  
  const entries = Array.from(monitoringState.foundLoads.entries());
  
  // Удаляем старые записи
  const freshEntries = entries.filter(([id, load]) => {
    return (now - load.foundAt) < maxAge;
  });
  
  // Если все еще много записей, оставляем только самые новые
  if (freshEntries.length > maxSize) {
    freshEntries.sort((a, b) => b[1].foundAt - a[1].foundAt);
    freshEntries.splice(maxSize);
  }
  
  // Пересоздаем Map с очищенными данными
  monitoringState.foundLoads.clear();
  freshEntries.forEach(([id, load]) => {
    monitoringState.foundLoads.set(id, load);
  });
  
  console.log(`Cache cleaned: ${entries.length} -> ${freshEntries.length} entries`);
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

// Парсинг данных груза из элемента
function parseLoadElement(element) {
  const loadData = {
    id: null,
    capacityType: null,
    pickup: null,
    delivery: null,
    pickupDate: null,
    deliveryDate: null,
    miles: 0,
    deadhead: 0,
    rate: 0,
    originRadius: null,
    destinationRadius: null,
    element: element
  };
  
  // Извлекаем ID груза
  let extractedId = extractText(element, SELECTORS.load_id);
  
  // Фильтруем некорректные ID (например, DLEFIELD, placeholder текст)
  if (extractedId && (
    extractedId.toLowerCase().includes('dlefield') ||
    extractedId.toLowerCase().includes('field') ||
    extractedId.toLowerCase().includes('placeholder') ||
    extractedId.toLowerCase().includes('enter') ||
    extractedId.length < 3 ||
    extractedId.length > 50
  )) {
    extractedId = null;
  }
  
  loadData.id = extractedId || generateLoadId(element);
  
  // Извлекаем тип груза
  loadData.capacityType = extractText(element, SELECTORS.capacity_type);
  
  // Извлекаем место погрузки
  loadData.pickup = extractText(element, SELECTORS.pickup_location);
  
  // Извлекаем место разгрузки
  loadData.delivery = extractText(element, SELECTORS.delivery_location);
  
  // Извлекаем даты
  loadData.pickupDate = extractText(element, SELECTORS.pickup_date);
  loadData.deliveryDate = extractText(element, SELECTORS.delivery_date);
  
  // Извлекаем мили
  const milesText = extractText(element, SELECTORS.miles);
  loadData.miles = parseNumber(milesText);
  
  // Извлекаем deadhead
  const deadheadText = extractText(element, SELECTORS.deadhead);
  loadData.deadhead = parseNumber(deadheadText);
  
  // Извлекаем ставку
  const rateText = extractText(element, SELECTORS.rate);
  loadData.rate = parseNumber(rateText);
  
  // Извлекаем радиусы
  const radiusElements = element.querySelectorAll(SELECTORS.radius.join(', '));
  if (radiusElements.length >= 2) {
    loadData.originRadius = extractRadius(radiusElements[0]);
    loadData.destinationRadius = extractRadius(radiusElements[1]);
  }
  
  // Валидация данных - теперь проверяем обязательные поля
  if (!loadData.pickup || !loadData.delivery) {
    console.warn('Missing pickup or delivery location:', loadData);
    return null;
  }
  
  // Если нет ID, генерируем уникальный на основе данных
  if (!loadData.id) {
    loadData.id = generateLoadId(loadData);
  }
  
  return loadData;
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

// Извлечение текста из элемента по селекторам
function extractText(parentElement, selectors) {
  for (const selector of selectors) {
    try {
      let elements = [];
      
      // Обработка специальных селекторов
      if (selector.includes(':contains(')) {
        // Парсим селектор с :contains()
        const match = selector.match(/(.*):\contains\("([^"]+)"\)(.*)/);
        if (match) {
          const [, prefix, text, suffix] = match;
          const baseSelector = prefix || '*';
          const candidates = parentElement.querySelectorAll(baseSelector);
          
          for (const el of candidates) {
            if (el.textContent && el.textContent.includes(text)) {
              if (suffix) {
                // Если есть суффикс (например, ~ * или + *), ищем соседние элементы
                if (suffix.trim() === '~ *') {
                  // Следующие соседние элементы
                  let sibling = el.nextElementSibling;
                  while (sibling) {
                    elements.push(sibling);
                    sibling = sibling.nextElementSibling;
                  }
                } else if (suffix.trim() === '+ *') {
                  // Непосредственно следующий элемент
                  if (el.nextElementSibling) {
                    elements.push(el.nextElementSibling);
                  }
                }
              } else {
                elements.push(el);
              }
            }
          }
        }
      } else {
        // Обычный селектор
        elements = Array.from(parentElement.querySelectorAll(selector));
      }
      
      // Проверяем найденные элементы
      for (const el of elements) {
        const text = extractTextFromElement(el);
        if (text) {
          return text;
        }
      }
    } catch (e) {
      // Игнорируем ошибки селекторов и продолжаем
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

// Расчет приоритета груза
function calculatePriority(loadData, profitability) {
  if (!profitability.isProfitable) {
    return 'LOW';
  }
  
  let score = 0;
  
  // Базовый балл за ставку за милю
  if (profitability.ratePerMile >= 4.0) score += 30;
  else if (profitability.ratePerMile >= 3.0) score += 20;
  else if (profitability.ratePerMile >= 2.5) score += 10;
  
  // Балл за короткий deadhead
  if (loadData.deadhead <= 10) score += 20;
  else if (loadData.deadhead <= 25) score += 15;
  else if (loadData.deadhead <= 50) score += 10;
  
  // Балл за хорошее расстояние
  if (loadData.miles >= 300 && loadData.miles <= 800) score += 15;
  else if (loadData.miles >= 200) score += 10;
  
  // Балл за общую прибыльность
  if (profitability.totalRevenue >= 2000) score += 15;
  else if (profitability.totalRevenue >= 1000) score += 10;
  
  // Определяем приоритет по общему баллу
  if (score >= 60) return 'HIGH';
  if (score >= 30) return 'MEDIUM';
  return 'LOW';
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
  
  // Фильтр по регионам (улучшенная версия)
  if (settings.regions && settings.regions.length > 0) {
    const matchesRegion = settings.regions.some(region => {
      const regionLower = region.trim().toLowerCase();
      
      // Пустые значения пропускаем
      if (!regionLower) return false;
      
      // Проверяем точное совпадение штатов (сокращения)
      if (regionLower.length === 2) {
        const regionUpper = regionLower.toUpperCase();
        // Проверяем в тексте pickup и delivery
        if ((load.pickup && load.pickup.includes(regionUpper)) || 
            (load.delivery && load.delivery.includes(regionUpper))) {
          return true;
        }
      }
      
      // Проверяем вхождение в названия городов/локаций
      const pickupMatch = load.pickup && load.pickup.toLowerCase().includes(regionLower);
      const deliveryMatch = load.delivery && load.delivery.toLowerCase().includes(regionLower);
      
      return pickupMatch || deliveryMatch;
    });
    
    if (!matchesRegion) {
      console.log('🚫 Load filtered out by region:', { 
        loadRegions: {
          pickup: load.pickup,
          delivery: load.delivery
        },
        filterRegions: settings.regions
      });
      return false;
    } else {
      console.log('✅ Load matches region filter:', {
        loadRegions: {
          pickup: load.pickup,
          delivery: load.delivery
        },
        filterRegions: settings.regions
      });
    }
  }
  
  return true;
}

// Адаптивная настройка интервала сканирования (оптимизированная версия)
function adjustScanInterval(result) {
  const currentInterval = monitoringState.adaptiveInterval;
  const baseInterval = monitoringState.settings?.scanInterval || 3000;
  let newInterval = currentInterval;
  
  switch (result) {
    case 'profitable_found':
      // Найдены прибыльные грузы - максимально ускоряем
      newInterval = Math.max(1500, currentInterval - 1000);
      break;
      
    case 'loads_found':
      // Найдены новые грузы - ускоряем сканирование
      newInterval = Math.max(2000, currentInterval - 500);
      break;
      
    case 'no_new_loads':
      // Новых грузов нет - замедляем сканирование
      newInterval = Math.min(baseInterval * 2, currentInterval + 1000);
      break;
      
    case 'no_loads':
      // Грузов вообще нет на странице - значительно замедляем
      newInterval = Math.min(baseInterval * 3, currentInterval + 2000);
      break;
      
    case 'error':
      // Ошибка сканирования - замедляем для снижения нагрузки
      newInterval = Math.min(baseInterval * 2.5, currentInterval + 1500);
      break;
      
    case 'slow_scan':
      // Медленное сканирование - увеличиваем интервал
      newInterval = Math.min(baseInterval * 2, currentInterval + 1000);
      break;
      
    default:
      // Возвращаем к базовому интервалу
      newInterval = baseInterval;
  }
  
  // Ограничиваем диапазон интервалов
  newInterval = Math.max(1500, Math.min(15000, newInterval));
  
  if (newInterval !== currentInterval) {
    console.log(`Scan interval adjusted: ${currentInterval}ms -> ${newInterval}ms (reason: ${result})`);
    monitoringState.adaptiveInterval = newInterval;
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
    'main': document.querySelector('main'),
    '#app': document.querySelector('#app'),
    '.search-results': document.querySelector('.search-results'),
    '[role="main"]': document.querySelector('[role="main"]'),
    '.content': document.querySelector('.content')
  };
  
  console.log('📦 Main containers found:');
  Object.entries(containers).forEach(([selector, element]) => {
    if (element) {
      console.log(`  ✅ ${selector} - ${element.className || element.id || element.tagName}`);
    }
  });
  
  // Ищем все элементы, которые могут быть карточками
  const potentialCards = [];
  
  // Поиск по классам
  const classPatterns = ['card', 'load', 'freight', 'result', 'item', 'row'];
  classPatterns.forEach(pattern => {
    const elements = document.querySelectorAll(`[class*="${pattern}"]`);
    if (elements.length > 0) {
      console.log(`🎯 Found ${elements.length} elements with class containing "${pattern}"`);
      elements.forEach(el => {
        if (el.textContent.length > 50 && el.childElementCount > 2) {
          potentialCards.push({
            element: el,
            selector: `[class*="${pattern}"]`,
            className: el.className
          });
        }
      });
    }
  });
  
  // Анализируем найденные потенциальные карточки
  console.log(`\n🃏 Found ${potentialCards.length} potential card elements:`);
  potentialCards.slice(0, 3).forEach((card, index) => {
    console.log(`\n📋 Card #${index + 1}:`);
    console.log(`  Selector: ${card.selector}`);
    console.log(`  Class: ${card.className}`);
    console.log(`  Children: ${card.element.childElementCount}`);
    console.log(`  Text preview: ${card.element.textContent.substring(0, 100).replace(/\s+/g, ' ')}...`);
    
    // Анализируем структуру
    const structure = analyzeElementStructure(card.element);
    console.log(`  Structure:`, structure);
  });
  
  // Проверяем наличие ключевых слов на странице
  const keywords = ['Origin', 'Destination', 'Capacity Type', 'miles', 'Romeoville', 'Dayville'];
  console.log('\n🔤 Keyword search:');
  keywords.forEach(keyword => {
    const count = (document.body.textContent.match(new RegExp(keyword, 'gi')) || []).length;
    if (count > 0) {
      console.log(`  ✅ "${keyword}" found ${count} times`);
    }
  });
  
  return potentialCards;
}

// Анализ структуры элемента
function analyzeElementStructure(element) {
  const structure = {
    tag: element.tagName,
    classes: element.className.split(' ').filter(c => c),
    hasOrigin: false,
    hasDestination: false,
    hasDate: false,
    hasMiles: false,
    hasPrice: false,
    textFields: []
  };
  
  // Рекурсивный поиск текстовых полей
  function findTextFields(el, depth = 0) {
    if (depth > 3) return; // Ограничиваем глубину
    
    for (const child of el.children) {
      const text = child.textContent.trim();
      
      if (text && child.children.length === 0) {
        structure.textFields.push({
          text: text.substring(0, 50),
          tag: child.tagName,
          class: child.className
        });
        
        // Проверяем содержимое
        if (text.includes('Origin')) structure.hasOrigin = true;
        if (text.includes('Destination')) structure.hasDestination = true;
        if (/\b\d{1,2}\/\d{1,2}\/\d{2,4}\b/.test(text) || /\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b/i.test(text)) structure.hasDate = true;
        if (/\b\d+\s*mi/i.test(text)) structure.hasMiles = true;
        if (/\$\d+/.test(text)) structure.hasPrice = true;
      }
      
      findTextFields(child, depth + 1);
    }
  }
  
  findTextFields(element);
  
  return structure;
}

// Добавляем команду для запуска диагностики через консоль
window.freightDiag = diagnosePage;
console.log('💡 Tip: Run "freightDiag()" in console to diagnose page structure');

console.log('FreightPower Load Monitor content script initialized');
