// FreightPower Load Monitor - Popup Script

// Утилита для debouncing
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// DOM элементы
const elements = {
  statusDot: document.getElementById('statusDot'),
  statusText: document.getElementById('statusText'),
  monitoringIcon: document.getElementById('monitoringIcon'),
  monitoringTitle: document.getElementById('monitoringTitle'),
  monitoringDescription: document.getElementById('monitoringDescription'),
  totalScans: document.getElementById('totalScans'),
  loadsFound: document.getElementById('loadsFound'),
  profitableLoads: document.getElementById('profitableLoads'),
  sessionsCount: document.getElementById('sessionsCount'),
  recentLoads: document.getElementById('recentLoads'),
  loadsList: document.getElementById('loadsList'),
  minRate: document.getElementById('minRate'),
  maxDeadhead: document.getElementById('maxDeadhead'),
  soundAlerts: document.getElementById('soundAlerts'),
  toggleMonitoring: document.getElementById('toggleMonitoring'),
  toggleText: document.getElementById('toggleText'),
  openOptions: document.getElementById('openOptions'),
  openFreightPower: document.getElementById('openFreightPower'),
  lastActivityText: document.getElementById('lastActivityText'),
  notification: document.getElementById('notification'),
  notificationIcon: document.getElementById('notificationIcon'),
  notificationText: document.getElementById('notificationText')
};

// Состояние приложения
let appState = {
  isActive: false,
  isLoggedIn: false,
  statistics: {},
  settings: {},
  recentLoads: [],
  isUpdating: false,
  isToggling: false
};

// Интервал обновления данных
let updateInterval = null;
let notificationTimeout = null;

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', async () => {
  console.log('Popup loaded');
  
  try {
    await loadData();
    setupEventListeners();
    updateUI();
    
    // Обновляем данные каждые 2 секунды
    updateInterval = setInterval(updateData, 2000);
  } catch (error) {
    console.error('Error initializing popup:', error);
    showNotification('❌', 'Ошибка инициализации', 'error');
  }
});

// Очистка ресурсов при закрытии
window.addEventListener('unload', () => {
  if (updateInterval) {
    clearInterval(updateInterval);
    updateInterval = null;
  }
  if (notificationTimeout) {
    clearTimeout(notificationTimeout);
    notificationTimeout = null;
  }
});

// Загрузка данных
async function loadData() {
  try {
    // Загружаем настройки
    const settingsResult = await chrome.storage.sync.get('settings');
    appState.settings = settingsResult.settings || {
      minRatePerMile: 2.5,
      maxDeadhead: 50,
      soundAlerts: true
    };
    
    // Загружаем статистику
    const statsResult = await chrome.storage.sync.get('statistics');
    appState.statistics = statsResult.statistics || {
      totalScans: 0,
      loadsFound: 0,
      profitableLoads: 0,
      sessionsCount: 0,
      lastActive: null
    };
    
    // Загружаем последние найденные грузы
    const loadsResult = await chrome.storage.local.get('recentLoads');
    appState.recentLoads = loadsResult.recentLoads || [];
    
    // Получаем статус мониторинга от background script
    try {
      const response = await chrome.runtime.sendMessage({ type: 'MONITORING_STATUS' });
      if (response && response.success !== false) {
        appState.isActive = response.isActive || false;
        appState.isLoggedIn = response.isLoggedIn || false;
      }
    } catch (error) {
      console.error('Error getting monitoring status:', error);
      // Пробуем получить статус через вкладки
      await checkFreightPowerTabs();
    }
    
    // Проверяем активные вкладки FreightPower
    await checkFreightPowerTabs();
    
  } catch (error) {
    console.error('Error loading data:', error);
    throw error;
  }
}

// Проверка активных вкладок FreightPower
async function checkFreightPowerTabs() {
  try {
    const tabs = await chrome.tabs.query({ 
      url: 'https://freightpower.schneider.com/*' 
    });
    
    if (tabs.length > 0) {
      // Есть активная вкладка FreightPower
      const tab = tabs[0];
      
      // Проверяем статус на вкладке
      try {
        const response = await chrome.tabs.sendMessage(tab.id, { type: 'GET_STATUS' });
        if (response && response.success !== false) {
          appState.isActive = response.isActive || false;
          appState.isLoggedIn = response.isLoggedIn || false;
        }
      } catch (error) {
        // Вкладка может быть не готова или content script не загружен
        console.log('Content script not ready on tab:', tab.id);
      }
    } else {
      // Нет активных вкладок FreightPower
      appState.isActive = false;
      appState.isLoggedIn = false;
    }
  } catch (error) {
    console.error('Error checking FreightPower tabs:', error);
  }
}

// Обновление данных
async function updateData() {
  // Предотвращаем одновременные обновления
  if (appState.isUpdating) {
    return;
  }
  
  appState.isUpdating = true;
  
  try {
    // Обновляем статистику
    const statsResult = await chrome.storage.sync.get('statistics');
    appState.statistics = statsResult.statistics || appState.statistics;
    
    // Обновляем статус мониторинга
    try {
      const response = await chrome.runtime.sendMessage({ type: 'MONITORING_STATUS' });
      if (response && response.success !== false) {
        const wasActive = appState.isActive;
        appState.isActive = response.isActive || false;
        appState.isLoggedIn = response.isLoggedIn || false;
        
        // Если статус изменился, обновляем UI
        if (wasActive !== appState.isActive) {
          updateUI();
        }
      }
    } catch (error) {
      // Background script может быть недоступен
      console.log('Background script not available:', error.message);
    }
    
    // Обновляем только статистику без полного обновления UI
    updateStatistics();
    updateLastActivity();
    
  } catch (error) {
    console.error('Error updating data:', error);
  } finally {
    appState.isUpdating = false;
  }
}

// Настройка обработчиков событий
function setupEventListeners() {
  // Создаем debounced версию сохранения настроек
  const debouncedSaveSettings = debounce(saveQuickSettings, 500);
  
  // Быстрые настройки
  elements.minRate.addEventListener('change', debouncedSaveSettings);
  elements.maxDeadhead.addEventListener('change', debouncedSaveSettings);
  elements.soundAlerts.addEventListener('change', debouncedSaveSettings);
  
  // Кнопки действий
  elements.toggleMonitoring.addEventListener('click', toggleMonitoring);
  elements.openOptions.addEventListener('click', openOptionsPage);
  elements.openFreightPower.addEventListener('click', openFreightPower);
  
  // Загружаем текущие настройки в поля
  loadSettingsToForm();
}

// Загрузка настроек в форму
function loadSettingsToForm() {
  if (appState.settings.minRatePerMile !== undefined) {
    elements.minRate.value = appState.settings.minRatePerMile;
  }
  if (appState.settings.maxDeadhead !== undefined) {
    elements.maxDeadhead.value = appState.settings.maxDeadhead;
  }
  if (appState.settings.soundAlerts !== undefined) {
    elements.soundAlerts.checked = appState.settings.soundAlerts;
  }
}

// Сохранение быстрых настроек
async function saveQuickSettings() {
  const newSettings = {
    ...appState.settings,
    minRatePerMile: parseFloat(elements.minRate.value) || 2.5,
    maxDeadhead: parseInt(elements.maxDeadhead.value) || 50,
    soundAlerts: elements.soundAlerts.checked
  };
  
  try {
    await chrome.storage.sync.set({ settings: newSettings });
    appState.settings = newSettings;
    
    // Уведомляем content script об изменении настроек
    try {
      const tabs = await chrome.tabs.query({ 
        url: 'https://freightpower.schneider.com/*' 
      });
      
      for (const tab of tabs) {
        try {
          await chrome.tabs.sendMessage(tab.id, {
            type: 'UPDATE_SETTINGS',
            settings: newSettings
          });
        } catch (error) {
          // Игнорируем ошибки отправки сообщений для неактивных вкладок
          console.log(`Could not update settings for tab ${tab.id}:`, error.message);
        }
      }
    } catch (error) {
      console.error('Error updating content script settings:', error);
    }
    
    showNotification('✅', 'Настройки сохранены', 'success');
  } catch (error) {
    console.error('Error saving settings:', error);
    showNotification('❌', 'Ошибка сохранения настроек', 'error');
  }
}

// Переключение мониторинга
async function toggleMonitoring() {
  // Предотвращаем множественные клики
  if (appState.isToggling) {
    return;
  }
  
  appState.isToggling = true;
  elements.toggleMonitoring.disabled = true;
  const originalText = elements.toggleText.textContent;
  elements.toggleText.textContent = 'Обработка...';
  
  try {
    const tabs = await chrome.tabs.query({ 
      url: 'https://freightpower.schneider.com/*' 
    });
    
    if (tabs.length === 0) {
      // Если нет открытых вкладок FreightPower
      if (!appState.isLoggedIn) {
        // Открываем FreightPower
        await openFreightPower();
      } else {
        showNotification('⚠️', 'Откройте FreightPower для мониторинга', 'warning');
      }
      return;
    }
    
    const tab = tabs[0];
    
    if (!appState.isLoggedIn) {
      showNotification('🔒', 'Сначала войдите в FreightPower', 'warning');
      return;
    }
    
    if (appState.isActive) {
      // Останавливаем мониторинг
      try {
        await chrome.tabs.sendMessage(tab.id, { type: 'STOP_MONITORING' });
        appState.isActive = false;
        showNotification('⏹️', 'Мониторинг остановлен', 'info');
      } catch (error) {
        console.error('Error stopping monitoring:', error);
        showNotification('❌', 'Ошибка остановки мониторинга', 'error');
      }
    } else {
      // Запускаем мониторинг
      try {
        await chrome.tabs.sendMessage(tab.id, { 
          type: 'START_MONITORING',
          settings: appState.settings
        });
        appState.isActive = true;
        showNotification('▶️', 'Мониторинг запущен', 'success');
      } catch (error) {
        console.error('Error starting monitoring:', error);
        showNotification('❌', 'Ошибка запуска мониторинга', 'error');
      }
    }
    
    updateUI();
    
  } catch (error) {
    console.error('Error toggling monitoring:', error);
    showNotification('❌', 'Ошибка переключения мониторинга', 'error');
  } finally {
    elements.toggleMonitoring.disabled = false;
    elements.toggleText.textContent = originalText;
    appState.isToggling = false;
  }
}

// Открытие страницы настроек
function openOptionsPage() {
  chrome.runtime.openOptionsPage();
}

// Открытие FreightPower
async function openFreightPower() {
  try {
    const tabs = await chrome.tabs.query({ 
      url: 'https://freightpower.schneider.com/*' 
    });
    
    if (tabs.length > 0) {
      // Переключаемся на существующую вкладку
      await chrome.tabs.update(tabs[0].id, { active: true });
      await chrome.windows.update(tabs[0].windowId, { focused: true });
    } else {
      // Создаем новую вкладку
      await chrome.tabs.create({ 
        url: 'https://freightpower.schneider.com' 
      });
    }
    
    // Закрываем popup
    window.close();
  } catch (error) {
    console.error('Error opening FreightPower:', error);
    showNotification('❌', 'Ошибка открытия FreightPower', 'error');
  }
}

// Обновление интерфейса
function updateUI() {
  updateStatus();
  updateStatistics();
  updateRecentLoads();
  updateLastActivity();
}

// Обновление статуса
function updateStatus() {
  if (!appState.isLoggedIn) {
    // Не авторизован
    elements.statusDot.className = 'status-dot offline';
    elements.statusText.textContent = 'Не авторизован';
    elements.monitoringIcon.textContent = '🔒';
    elements.monitoringTitle.textContent = 'Требуется авторизация';
    elements.monitoringDescription.textContent = 'Войдите в FreightPower для запуска мониторинга';
    elements.toggleText.textContent = 'Открыть FreightPower';
    elements.toggleMonitoring.className = 'btn btn-secondary';
    elements.toggleMonitoring.disabled = false;
  } else if (appState.isActive) {
    // Активен
    elements.statusDot.className = 'status-dot online';
    elements.statusText.textContent = 'Активен';
    elements.monitoringIcon.textContent = '▶️';
    elements.monitoringTitle.textContent = 'Мониторинг активен';
    elements.monitoringDescription.textContent = 'Автоматический поиск прибыльных грузов';
    elements.toggleText.textContent = 'Остановить мониторинг';
    elements.toggleMonitoring.className = 'btn btn-danger';
    elements.toggleMonitoring.disabled = false;
  } else {
    // Остановлен но авторизован
    elements.statusDot.className = 'status-dot idle';
    elements.statusText.textContent = 'Остановлен';
    elements.monitoringIcon.textContent = '⏸️';
    elements.monitoringTitle.textContent = 'Мониторинг остановлен';
    elements.monitoringDescription.textContent = 'Нажмите для запуска автоматического мониторинга';
    elements.toggleText.textContent = 'Запустить мониторинг';
    elements.toggleMonitoring.className = 'btn btn-primary';
    elements.toggleMonitoring.disabled = false;
  }
}

// Обновление статистики
function updateStatistics() {
  const stats = appState.statistics;
  
  elements.totalScans.textContent = formatNumber(stats.totalScans || 0);
  elements.loadsFound.textContent = formatNumber(stats.loadsFound || 0);
  elements.profitableLoads.textContent = formatNumber(stats.profitableLoads || 0);
  elements.sessionsCount.textContent = formatNumber(stats.sessionsCount || 0);
}

// Обновление последних найденных грузов
function updateRecentLoads() {
  if (!appState.recentLoads || appState.recentLoads.length === 0) {
    elements.recentLoads.style.display = 'none';
    return;
  }
  
  elements.recentLoads.style.display = 'block';
  elements.loadsList.innerHTML = '';
  
  // Показываем последние 3 груза
  const recentLoads = appState.recentLoads.slice(0, 3);
  
  recentLoads.forEach(load => {
    const loadElement = createLoadElement(load);
    elements.loadsList.appendChild(loadElement);
  });
}

// Создание элемента груза
function createLoadElement(load) {
  const div = document.createElement('div');
  div.className = 'load-item';
  
  const priorityIcon = load.priority === 'HIGH' ? '🔥' : '💰';
  const priorityClass = load.priority === 'HIGH' ? 'high-priority' : 'medium-priority';
  
  // Безопасное отображение данных
  const loadId = load.id || 'N/A';
  const pickup = load.pickup || 'N/A';
  const delivery = load.delivery || 'N/A';
  const ratePerMile = load.ratePerMile ? load.ratePerMile.toFixed(2) : '0.00';
  const miles = load.miles || 0;
  const deadhead = load.deadhead || 0;
  
  div.innerHTML = `
    <div class="load-header">
      <span class="load-priority ${priorityClass}">${priorityIcon}</span>
      <span class="load-id">${escapeHtml(loadId)}</span>
      <span class="load-time">${formatTime(load.foundAt)}</span>
    </div>
    <div class="load-route">
      <span class="pickup">${escapeHtml(pickup)}</span>
      <span class="arrow">→</span>
      <span class="delivery">${escapeHtml(delivery)}</span>
    </div>
    <div class="load-details">
      <span class="rate">$${ratePerMile}/миля</span>
      <span class="miles">${miles} миль</span>
      <span class="deadhead">DH: ${deadhead}</span>
    </div>
  `;
  
  return div;
}

// Экранирование HTML для безопасности
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Обновление информации о последней активности
function updateLastActivity() {
  const lastActive = appState.statistics.lastActive;
  
  if (lastActive) {
    const timeAgo = getTimeAgo(lastActive);
    elements.lastActivityText.textContent = `Последняя активность: ${timeAgo}`;
  } else {
    elements.lastActivityText.textContent = 'Последняя активность: никогда';
  }
}

// Показ уведомления
function showNotification(icon, text, type = 'info') {
  // Очищаем предыдущий таймаут
  if (notificationTimeout) {
    clearTimeout(notificationTimeout);
  }
  
  elements.notificationIcon.textContent = icon;
  elements.notificationText.textContent = text;
  elements.notification.className = `notification ${type}`;
  elements.notification.style.display = 'block';
  
  // Скрываем через 3 секунды
  notificationTimeout = setTimeout(() => {
    elements.notification.style.display = 'none';
    notificationTimeout = null;
  }, 3000);
}

// Утилиты для форматирования
function formatNumber(num) {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M';
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K';
  }
  return num.toString();
}

function formatTime(timestamp) {
  if (!timestamp) return 'никогда';
  
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  
  if (diffMins < 1) return 'только что';
  if (diffMins < 60) return `${diffMins}м назад`;
  
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}ч назад`;
  
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}д назад`;
}

function getTimeAgo(timestamp) {
  if (!timestamp) return 'никогда';
  
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  
  if (diffMins < 1) return 'только что';
  if (diffMins < 60) return `${diffMins} минут назад`;
  
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours} часов назад`;
  
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays} дней назад`;
  
  return date.toLocaleDateString('ru-RU');
}

// Обработка сообщений от background script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  try {
    switch (message.type) {
      case 'LOAD_FOUND':
        // Добавляем новый груз в список
        if (!appState.recentLoads) {
          appState.recentLoads = [];
        }
        
        appState.recentLoads.unshift(message.data);
        
        // Ограничиваем список 10 элементами
        if (appState.recentLoads.length > 10) {
          appState.recentLoads = appState.recentLoads.slice(0, 10);
        }
        
        // Сохраняем в local storage
        chrome.storage.local.set({ recentLoads: appState.recentLoads })
          .catch(error => console.error('Error saving recent loads:', error));
        
        // Обновляем UI
        updateRecentLoads();
        break;
        
      case 'MONITORING_STATUS_CHANGED':
        appState.isActive = message.isActive || false;
        appState.isLoggedIn = message.isLoggedIn || false;
        updateUI();
        break;
        
      case 'STATISTICS_UPDATED':
        if (message.statistics) {
          appState.statistics = message.statistics;
          updateStatistics();
          updateLastActivity();
        }
        break;
    }
  } catch (error) {
    console.error('Error handling message:', error);
  }
  
  // Всегда отправляем ответ для предотвращения ошибок
  sendResponse({ success: true });
  return true;
});

console.log('Popup script initialized');
