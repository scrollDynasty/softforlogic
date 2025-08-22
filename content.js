// Content Script для автоматического мониторинга FreightPower
class FreightPowerMonitor {
  constructor() {
    this.isMonitoring = false;
    this.scanInterval = null;
    this.foundLoads = new Set();
    this.settings = {};
    this.statistics = {};
    
    this.SELECTORS = {
      load_items: [
        '[data-testid="load-row"]',
        '.load-item, .freight-item',
        'tr[class*="load"], tbody tr',
        '.search-results tr'
      ],
      load_id: [
        '[data-testid="reference"]',
        '.load-reference, .id-column',
        'td:first-child'
      ],
      pickup_location: [
        '[data-testid="pickup-location"]',
        '.origin, .pickup, .pickup-location',
        'td:nth-child(2)'
      ],
      delivery_location: [
        '[data-testid="delivery-location"]',
        '.destination, .delivery, .delivery-location',
        'td:nth-child(3)'
      ],
      miles: [
        '[data-testid="miles"]',
        '.distance, .total-miles, .miles-column',
        'td:nth-child(4)'
      ],
      deadhead: [
        '[data-testid="deadhead"]',
        '.deadhead, .empty-miles',
        'td:nth-child(5)'
      ],
      rate: [
        '[data-testid="rate"]',
        '.rate, .price, .pay, .freight-rate',
        'td:nth-child(6)'
      ]
    };
    
    this.init();
  }
  
  async init() {
    await this.loadSettings();
    this.setupMessageListeners();
    this.checkLoginStatus();
    
    // Наблюдаем за изменениями DOM для детекции авторизации
    this.observeDOMChanges();
  }
  
  async loadSettings() {
    return new Promise((resolve) => {
      chrome.storage.local.get(['settings'], (result) => {
        this.settings = result.settings || {
          minRatePerMile: 2.50,
          maxDeadhead: 50,
          minDistance: 200,
          maxDistance: null,
          equipmentTypes: ['Dry Van', 'Reefer', 'Flatbed'],
          scanInterval: 3000,
          enableNotifications: true,
          enableSound: true
        };
        resolve();
      });
    });
  }
  
  setupMessageListeners() {
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
      switch (message.type) {
        case 'CHECK_LOGIN_STATUS':
          this.checkLoginStatus();
          break;
          
        case 'START_MONITORING':
          this.startMonitoring();
          break;
          
        case 'STOP_MONITORING':
          this.stopMonitoring();
          break;
          
        case 'UPDATE_SETTINGS':
          this.updateSettings(message.settings);
          break;
          
        case 'GET_STATUS':
          sendResponse({
            isMonitoring: this.isMonitoring,
            statistics: this.statistics
          });
          break;
      }
    });
  }
  
  observeDOMChanges() {
    // Наблюдаем за изменениями в DOM для детекции авторизации/выхода
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.type === 'childList') {
          // Проверяем, не появились ли элементы авторизации
          if (this.detectLogin()) {
            this.onLoginDetected();
          } else if (this.detectLogout()) {
            this.onLogoutDetected();
          }
        }
      });
    });
    
    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }
  
  detectLogin() {
    return window.location.href.includes('freightpower.schneider.com') && 
           (document.querySelector('[data-user-authenticated]') ||
            document.querySelector('.dashboard') ||
            document.querySelector('.user-menu') ||
            document.querySelector('.logout') ||
            document.querySelector('[data-testid="user-menu"]') ||
            localStorage.getItem('userToken') ||
            sessionStorage.getItem('authToken') ||
            document.cookie.includes('session') ||
            document.cookie.includes('auth'));
  }
  
  detectLogout() {
    return !this.detectLogin() && 
           (window.location.href.includes('login') ||
            window.location.href.includes('signin') ||
            document.querySelector('.login-form') ||
            document.querySelector('[data-testid="login"]'));
  }
  
  checkLoginStatus() {
    if (this.detectLogin()) {
      this.onLoginDetected();
    } else if (this.detectLogout()) {
      this.onLogoutDetected();
    }
  }
  
  onLoginDetected() {
    console.log('Авторизация обнаружена - запускаем мониторинг');
    chrome.runtime.sendMessage({ type: 'LOGIN_DETECTED' });
    this.startMonitoring();
  }
  
  onLogoutDetected() {
    console.log('Выход обнаружен - останавливаем мониторинг');
    chrome.runtime.sendMessage({ type: 'LOGOUT_DETECTED' });
    this.stopMonitoring();
  }
  
  startMonitoring() {
    if (this.isMonitoring) return;
    
    this.isMonitoring = true;
    this.scanInterval = setInterval(() => {
      this.scanForLoads();
    }, this.settings.scanInterval);
    
    console.log('Мониторинг грузов запущен');
  }
  
  stopMonitoring() {
    if (!this.isMonitoring) return;
    
    this.isMonitoring = false;
    if (this.scanInterval) {
      clearInterval(this.scanInterval);
      this.scanInterval = null;
    }
    
    console.log('Мониторинг грузов остановлен');
  }
  
  scanForLoads() {
    try {
      const loadElements = this.findLoadElements();
      
      loadElements.forEach((element) => {
        const load = this.parseLoadElement(element);
        if (load && !this.foundLoads.has(load.loadId)) {
          this.foundLoads.add(load.loadId);
          this.processLoad(load);
        }
      });
    } catch (error) {
      console.error('Ошибка при сканировании грузов:', error);
    }
  }
  
  findLoadElements() {
    const elements = [];
    
    this.SELECTORS.load_items.forEach((selector) => {
      const found = document.querySelectorAll(selector);
      found.forEach((el) => {
        if (el && !elements.includes(el)) {
          elements.push(el);
        }
      });
    });
    
    return elements;
  }
  
  parseLoadElement(element) {
    try {
      const loadId = this.extractText(element, this.SELECTORS.load_id);
      const pickupLocation = this.extractText(element, this.SELECTORS.pickup_location);
      const deliveryLocation = this.extractText(element, this.SELECTORS.delivery_location);
      const miles = this.extractNumber(element, this.SELECTORS.miles);
      const deadhead = this.extractNumber(element, this.SELECTORS.deadhead);
      const rate = this.extractNumber(element, this.SELECTORS.rate);
      
      if (!loadId || !pickupLocation || !deliveryLocation || !miles || !rate) {
        return null;
      }
      
      return {
        loadId: loadId.trim(),
        pickupLocation: pickupLocation.trim(),
        deliveryLocation: deliveryLocation.trim(),
        miles: miles,
        deadhead: deadhead || 0,
        rate: rate,
        timestamp: Date.now()
      };
    } catch (error) {
      console.error('Ошибка при парсинге элемента груза:', error);
      return null;
    }
  }
  
  extractText(element, selectors) {
    for (const selector of selectors) {
      const found = element.querySelector(selector);
      if (found && found.textContent) {
        return found.textContent.trim();
      }
    }
    return null;
  }
  
  extractNumber(element, selectors) {
    const text = this.extractText(element, selectors);
    if (!text) return null;
    
    // Извлекаем числа из текста (удаляем символы валюты, запятые и т.д.)
    const number = parseFloat(text.replace(/[$,]/g, ''));
    return isNaN(number) ? null : number;
  }
  
  processLoad(load) {
    // Рассчитываем прибыльность
    load.profitability = this.calculateProfitability(load);
    
    // Проверяем фильтры
    if (this.passesFilters(load)) {
      console.log('Найден прибыльный груз:', load);
      chrome.runtime.sendMessage({
        type: 'LOAD_FOUND',
        load: load
      });
    }
  }
  
  calculateProfitability(load) {
    const totalMiles = load.miles + load.deadhead;
    const ratePerMile = load.rate / totalMiles;
    const deadheadRatio = load.deadhead / load.miles;
    
    const profitabilityScore = ratePerMile * (1 - deadheadRatio * 0.3);
    
    return {
      ratePerMile: Math.round(ratePerMile * 100) / 100,
      profitabilityScore: Math.round(profitabilityScore * 100) / 100,
      isProfitable: ratePerMile >= this.settings.minRatePerMile && 
                   deadheadRatio <= (this.settings.maxDeadhead / load.miles),
      priority: profitabilityScore > 3 ? 'HIGH' : 'MEDIUM'
    };
  }
  
  passesFilters(load) {
    const totalMiles = load.miles + load.deadhead;
    
    // Проверяем минимальную ставку за милю
    if (load.profitability.ratePerMile < this.settings.minRatePerMile) {
      return false;
    }
    
    // Проверяем максимальный deadhead
    if (load.deadhead > this.settings.maxDeadhead) {
      return false;
    }
    
    // Проверяем минимальное расстояние
    if (load.miles < this.settings.minDistance) {
      return false;
    }
    
    // Проверяем максимальное расстояние (если установлено)
    if (this.settings.maxDistance && load.miles > this.settings.maxDistance) {
      return false;
    }
    
    return true;
  }
  
  // Метод для обновления настроек
  updateSettings(newSettings) {
    this.settings = { ...this.settings, ...newSettings };
    
    // Перезапускаем мониторинг с новыми настройками
    if (this.isMonitoring) {
      this.stopMonitoring();
      this.startMonitoring();
    }
  }
}

// Инициализация мониторинга
const monitor = new FreightPowerMonitor();

// Экспортируем для доступа из popup
window.freightPowerMonitor = monitor;
