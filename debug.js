// FreightPower Load Monitor - Debug Utilities

// Глобальная функция диагностики
window.freightDiag = function() {
  console.log('🔍 FreightPower Load Monitor - Диагностика');
  console.log('==========================================');
  
  // Проверяем состояние расширения
  console.log('📊 Состояние расширения:');
  console.log('- URL:', window.location.href);
  console.log('- Заголовок страницы:', document.title);
  console.log('- Время загрузки:', new Date().toLocaleString());
  
  // Проверяем наличие элементов авторизации
  const authElements = [
    { selector: '[data-user-authenticated="true"]', name: 'data-user-authenticated (true)' },
    { selector: '[data-user-id]', name: 'data-user-id' },
    { selector: '.user-avatar', name: 'user-avatar' },
    { selector: '.profile-dropdown', name: 'profile-dropdown' },
    { selector: '[class*="user-profile"]', name: 'user-profile' },
    { selector: '[class*="account-menu"]', name: 'account-menu' },
    { selector: '.logout', name: 'logout button' },
    { selector: '[href*="logout"]', name: 'logout link' },
    { selector: '.dashboard', name: 'dashboard' },
    { selector: '.user-menu', name: 'user-menu' },
    { selector: '.header-user', name: 'header-user' },
    { selector: '[class*="user-nav"]', name: 'user-nav' },
    { selector: '[class*="profile"]', name: 'profile' },
    { selector: 'nav[class*="user"]', name: 'user nav' },
    { selector: '[class*="logged-in"]', name: 'logged-in' },
    { selector: '[class*="authenticated"]', name: 'authenticated' }
  ];
  
  console.log('🔐 Элементы авторизации:');
  authElements.forEach(item => {
    const element = document.querySelector(item.selector);
    console.log(`- ${item.name}: ${element ? '✅ Найден' : '❌ Не найден'}`);
    if (element) {
      console.log(`  └── Тег: ${element.tagName}, Классы: ${element.className || 'нет'}`);
    }
  });
  
  // Расширенная проверка storage
  console.log('💾 Storage (расширенная проверка):');
  const authStorageKeys = [
    'userToken', 'authToken', 'auth', 'accessToken', 'jwt',
    'session', 'user', 'userData', 'schneider_auth', 
    'freightpower_auth', 'auth_token', 'bearer_token',
    'access_token', 'refresh_token', 'authorization'
  ];
  
  authStorageKeys.forEach(key => {
    const localValue = localStorage.getItem(key);
    const sessionValue = sessionStorage.getItem(key);
    const hasLocal = localValue && localValue !== 'null' && localValue !== 'undefined';
    const hasSession = sessionValue && sessionValue !== 'null' && sessionValue !== 'undefined';
    
    if (hasLocal || hasSession) {
      console.log(`- ${key}: ✅ ${hasLocal ? 'localStorage' : ''}${hasLocal && hasSession ? ' + ' : ''}${hasSession ? 'sessionStorage' : ''}`);
      if (hasLocal) console.log(`  └── localStorage: ${localValue.substring(0, 50)}${localValue.length > 50 ? '...' : ''}`);
      if (hasSession) console.log(`  └── sessionStorage: ${sessionValue.substring(0, 50)}${sessionValue.length > 50 ? '...' : ''}`);
    } else {
      console.log(`- ${key}: ❌`);
    }
  });
  
  // Расширенная проверка cookies
  console.log('🍪 Cookies (расширенная проверка):');
  const authCookiePatterns = [
    'auth', 'session', 'token', 'jwt', 'bearer',
    'schneider', 'freightpower', 'user', 'access'
  ];
  
  authCookiePatterns.forEach(pattern => {
    const cookies = document.cookie.toLowerCase();
    const regex = new RegExp(`${pattern}[^=]*=([^;]+)`);
    const match = cookies.match(regex);
    const hasValue = match && match[1] && match[1].trim() !== '' && match[1] !== 'null';
    
    if (hasValue) {
      console.log(`- ${pattern} cookie: ✅`);
      console.log(`  └── Значение: ${match[1].substring(0, 50)}${match[1].length > 50 ? '...' : ''}`);
    } else {
      console.log(`- ${pattern} cookie: ❌`);
    }
  });
  
  // Проверяем формы входа
  console.log('🔒 Формы входа:');
  const loginFormElements = [
    { selector: 'input[name="password"]', name: 'password input (name)' },
    { selector: 'input[type="password"]', name: 'password input (type)' },
    { selector: '.login-form', name: 'login-form' },
    { selector: 'form[action*="login"]', name: 'login action form' },
    { selector: 'form[action*="signin"]', name: 'signin action form' },
    { selector: '[class*="signin-form"]', name: 'signin-form' },
    { selector: '[class*="login-container"]', name: 'login-container' }
  ];
  
  loginFormElements.forEach(item => {
    const element = document.querySelector(item.selector);
    console.log(`- ${item.name}: ${element ? '⚠️ Найден' : '✅ Не найден'}`);
  });
  
  // Ищем контейнеры с результатами
  const containers = [
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
  
  console.log('📦 Контейнеры результатов:');
  containers.forEach(selector => {
    const element = document.querySelector(selector);
    console.log(`- ${selector}: ${element ? '✅ Найден' : '❌ Не найден'}`);
  });
  
  // Ищем карточки грузов
  const loadSelectors = [
    '[class*="card"][class*="load"]',
    '[class*="load-card"]',
    '[class*="freight-card"]',
    '[class*="search-result-card"]',
    '[class*="result-item"]',
    'div[class*="load"][class*="item"]',
    'article[class*="load"]',
    '.card',
    '[data-testid="load-row"]',
    '.load-item, .freight-item',
    'tr[class*="load"], tbody tr',
    '.search-results tr',
    '[class*="row"][class*="load"]',
    'table tbody tr'
  ];
  
  console.log('📋 Карточки грузов:');
  loadSelectors.forEach(selector => {
    const elements = document.querySelectorAll(selector);
    if (elements.length > 0) {
      console.log(`- ${selector}: ${elements.length} элементов`);
      
      // Показываем первые 3 элемента
      Array.from(elements).slice(0, 3).forEach((el, index) => {
        const text = el.textContent.substring(0, 100) + (el.textContent.length > 100 ? '...' : '');
        console.log(`  ${index + 1}. ${text}`);
      });
    } else {
      console.log(`- ${selector}: ❌ Не найдено`);
    }
  });
  
  // Эвристический поиск
  console.log('🔍 Эвристический поиск:');
  const allElements = document.querySelectorAll('div, article, section, tr');
  const potentialLoads = Array.from(allElements).filter(el => {
    const text = el.textContent || '';
    const hasOrigin = text.includes('Origin') || /\b[A-Z][a-z]+(?:ville|ton|burg|city|town)\b/.test(text);
    const hasDestination = text.includes('Destination') || text.split(',').length > 2;
    const hasState = /\b[A-Z]{2}\b/.test(text);
    const hasMiles = /\b\d+\s*mi/i.test(text) || text.includes('miles');
    const hasDate = /\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}/i.test(text);
    const score = [hasOrigin, hasDestination, hasState, hasMiles, hasDate].filter(Boolean).length;
    return score >= 2 && el.childElementCount > 2;
  });
  
  console.log(`- Потенциальных грузов найдено: ${potentialLoads.length}`);
  
  // Проверяем наличие расширения
  console.log('🔧 Расширение:');
  if (typeof chrome !== 'undefined' && chrome.runtime) {
    console.log('- Chrome API: ✅ Доступен');
    console.log('- Extension ID:', chrome.runtime.id);
    
    // Проверяем background script
    chrome.runtime.sendMessage({ type: 'MONITORING_STATUS' })
      .then(response => {
        console.log('- Background script: ✅ Отвечает');
        console.log('- Состояние мониторинга:', response);
      })
      .catch(error => {
        console.log('- Background script: ❌ Не отвечает');
        console.log('- Ошибка:', error.message);
      });
  } else {
    console.log('- Chrome API: ❌ Недоступен');
  }
  
  console.log('==========================================');
  console.log('💡 Для получения дополнительной информации используйте:');
  console.log('- freightDiag().loads - показать найденные грузы');
  console.log('- freightDiag().elements - показать все элементы');
  console.log('- freightDiag().test() - запустить тест парсинга');
};

// Дополнительные функции диагностики
window.freightDiag.loads = function() {
  console.log('📋 Анализ найденных грузов:');
  
  const loadElements = findLoadElements();
  console.log(`Найдено элементов: ${loadElements.length}`);
  
  loadElements.forEach((element, index) => {
    console.log(`\n--- Груз ${index + 1} ---`);
    console.log('HTML:', element.outerHTML.substring(0, 500) + '...');
    console.log('Текст:', element.textContent.substring(0, 200) + '...');
    
    try {
      const loadData = parseLoadElement(element);
      console.log('Парсинг:', loadData);
    } catch (error) {
      console.log('Ошибка парсинга:', error.message);
    }
  });
};

window.freightDiag.elements = function() {
  console.log('🔍 Все элементы на странице:');
  
  const allElements = document.querySelectorAll('*');
  const elementsWithText = Array.from(allElements).filter(el => {
    const text = el.textContent || '';
    return text.length > 10 && text.length < 200 && 
           (text.includes('Origin') || text.includes('Destination') || 
            text.includes('miles') || /\$\d+/.test(text));
  });
  
  console.log(`Элементов с релевантным текстом: ${elementsWithText.length}`);
  
  elementsWithText.slice(0, 10).forEach((el, index) => {
    console.log(`\n${index + 1}. ${el.tagName}.${el.className}`);
    console.log('Текст:', el.textContent.trim());
  });
};

window.freightDiag.test = function() {
  console.log('🧪 Тест парсинга:');
  
  const loadElements = findLoadElements();
  if (loadElements.length === 0) {
    console.log('❌ Нет элементов для тестирования');
    return;
  }
  
  const testElement = loadElements[0];
  console.log('Тестируем элемент:', testElement);
  
  try {
    const loadData = parseLoadElement(testElement);
    console.log('✅ Парсинг успешен:', loadData);
    
    const profitability = calculateProfitability(loadData);
    console.log('💰 Прибыльность:', profitability);
    
    const passes = passesFilters(loadData, profitability);
    console.log('✅ Проходит фильтры:', passes);
    
  } catch (error) {
    console.log('❌ Ошибка парсинга:', error);
  }
};

// Функции для поиска элементов (копии из content.js)
function findLoadElements() {
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
      break;
    }
  }
  
  const loadSelectors = [
    '[class*="card"][class*="load"]',
    '[class*="load-card"]',
    '[class*="freight-card"]',
    '[class*="search-result-card"]',
    '[class*="result-item"]',
    'div[class*="load"][class*="item"]',
    'article[class*="load"]',
    '.card',
    '[data-testid="load-row"]',
    '.load-item, .freight-item',
    'tr[class*="load"], tbody tr',
    '.search-results tr',
    '[class*="row"][class*="load"]',
    'table tbody tr'
  ];
  
  for (const selector of loadSelectors) {
    const elements = container.querySelectorAll(selector);
    if (elements.length > 0) {
      return Array.from(elements);
    }
  }
  
  return [];
}

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
  
  // Простой парсинг для тестирования
  const text = element.textContent || '';
  
  // Ищем ID
  const idMatch = text.match(/(?:ID|Reference|Load)\s*[#:]?\s*([A-Z0-9-]+)/i);
  if (idMatch) loadData.id = idMatch[1];
  
  // Ищем города
  const cityMatch = text.match(/([A-Z][a-z]+(?:ville|ton|burg|city|town)?),\s*([A-Z]{2})/g);
  if (cityMatch && cityMatch.length >= 2) {
    loadData.pickup = cityMatch[0];
    loadData.delivery = cityMatch[1];
  }
  
  // Ищем мили
  const milesMatch = text.match(/(\d+)\s*mi/i);
  if (milesMatch) loadData.miles = parseInt(milesMatch[1]);
  
  // Ищем ставку
  const rateMatch = text.match(/\$(\d+(?:,\d+)*(?:\.\d{2})?)/);
  if (rateMatch) loadData.rate = parseFloat(rateMatch[1].replace(/,/g, ''));
  
  return loadData;
}

function calculateProfitability(load) {
  const totalMiles = load.miles + load.deadhead;
  const ratePerMile = totalMiles > 0 ? load.rate / totalMiles : 0;
  const deadheadRatio = load.miles > 0 ? load.deadhead / load.miles : 1;
  
  return {
    ratePerMile,
    profitabilityScore: ratePerMile * (1 - deadheadRatio * 0.3),
    deadheadRatio,
    isProfitable: ratePerMile >= 2.50 && deadheadRatio <= 0.25,
    priority: ratePerMile > 3.5 ? 'HIGH' : ratePerMile > 2.5 ? 'MEDIUM' : 'LOW'
  };
}

function passesFilters(load, profitability) {
  return profitability.ratePerMile >= 2.50 && load.deadhead <= 50;
}

console.log('🔧 FreightPower Load Monitor - Debug utilities loaded');
console.log('💡 Используйте freightDiag() для диагностики');
