// FreightPower Load Monitor - Popup Script

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
  recentLoads: []
};

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', async () => {
  console.log('Popup loaded');
  
  await loadData();
  setupEventListeners();
  updateUI();
  
  // Обновляем данные каждые 2 секунды
  setInterval(updateData, 2000);
});

// Загрузка данных
async function loadData() {
  try {
    // Загружаем настройки
    const settingsResult = await chrome.storage.sync.get('settings');
    appState.settings = settingsResult.settings || {};
    
    // Загружаем статистику
    const statsResult = await chrome.storage.sync.get('statistics');
    appState.statistics = statsResult.statistics || {};
    
    // Загружаем последние найденные грузы
    const loadsResult = await chrome.storage.local.get('recentLoads');
    appState.recentLoads = loadsResult.recentLoads || [];
    
    // Получаем статус мониторинга от background script
    try {
      const response = await chrome.runtime.sendMessage({ type: 'MONITORING_STATUS' });
      if (response) {
        appState.isActive = response.isActive || false;
        appState.isLoggedIn = response.isLoggedIn || false;
      }
    } catch (error) {
      console.error('Error getting monitoring status:', error);
    }
    
    // Проверяем активные вкладки FreightPower
    await checkFreightPowerTabs();
    
  } catch (error) {
    console.error('Error loading data:', error);
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
        if (response) {
          appState.isActive = response.isActive || false;
          appState.isLoggedIn = response.isLoggedIn || false;
        }
      } catch (error) {
        // Вкладка может быть не готова или content script не загружен
        console.log('Content script not ready on tab:', tab.id);
      }
    }
  } catch (error) {
    console.error('Error checking FreightPower tabs:', error);
  }
}

// Обновление данных
async function updateData() {
  try {
    // Обновляем статистику
    const statsResult = await chrome.storage.sync.get('statistics');
    appState.statistics = statsResult.statistics || {};
    
    // Обновляем статус мониторинга
    try {
      const response = await chrome.runtime.sendMessage({ type: 'MONITORING_STATUS' });
      if (response) {
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
    }
    
    // Обновляем только статистику без полного обновления UI
    updateStatistics();
    
  } catch (error) {
    console.error('Error updating data:', error);
  }
}

// Настройка обработчиков событий
function setupEventListeners() {
  // Быстрые настройки
  elements.minRate.addEventListener('change', saveQuickSettings);
  elements.maxDeadhead.addEventListener('change', saveQuickSettings);
  elements.soundAlerts.addEventListener('change', saveQuickSettings);
  
  // Кнопки действий
  elements.toggleMonitoring.addEventListener('click', toggleMonitoring);
  elements.openOptions.addEventListener('click', openOptionsPage);
  elements.openFreightPower.addEventListener('click', openFreightPower);
  
  // Загружаем текущие настройки в поля
  loadSettingsToForm();
}

// Загрузка настроек в форму
function loadSettingsToForm() {
  if (appState.settings.minRatePerMile) {
    elements.minRate.value = appState.settings.minRatePerMile;
  }
  if (appState.settings.maxDeadhead) {
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
          // Игнорируем ошибки отправки сообщений
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
  try {
    const tabs = await chrome.tabs.query({ 
      url: 'https://freightpower.schneider.com/*' 
    });
    
    if (tabs.length === 0) {
      showNotification('⚠️', 'Откройте FreightPower для мониторинга', 'warning');
      return;
    }
    
    const tab = tabs[0];
    
    if (appState.isActive) {
      // Останавливаем мониторинг
      await chrome.tabs.sendMessage(tab.id, { type: 'STOP_MONITORING' });
      appState.isActive = false;
      showNotification('⏹️', 'Мониторинг остановлен', 'info');
    } else {
      // Запускаем мониторинг
      await chrome.tabs.sendMessage(tab.id, { 
        type: 'START_MONITORING',
        settings: appState.settings
      });
      appState.isActive = true;
      showNotification('▶️', 'Мониторинг запущен', 'success');
    }
    
    updateUI();
    
  } catch (error) {
    console.error('Error toggling monitoring:', error);
    showNotification('❌', 'Ошибка переключения мониторинга', 'error');
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
  if (appState.recentLoads.length === 0) {
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
  
  div.innerHTML = `
    <div class="load-header">
      <span class="load-priority ${priorityClass}">${priorityIcon}</span>
      <span class="load-id">${load.id}</span>
      <span class="load-time">${formatTime(load.foundAt)}</span>
    </div>
    <div class="load-route">
      <span class="pickup">${load.pickup || 'N/A'}</span>
      <span class="arrow">→</span>
      <span class="delivery">${load.delivery || 'N/A'}</span>
    </div>
    <div class="load-details">
      <span class="rate">$${load.ratePerMile?.toFixed(2)}/миля</span>
      <span class="miles">${load.miles} миль</span>
      <span class="deadhead">DH: ${load.deadhead}</span>
    </div>
  `;
  
  return div;
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
  elements.notificationIcon.textContent = icon;
  elements.notificationText.textContent = text;
  elements.notification.className = `notification ${type}`;
  elements.notification.style.display = 'block';
  
  // Скрываем через 3 секунды
  setTimeout(() => {
    elements.notification.style.display = 'none';
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
  switch (message.type) {
    case 'LOAD_FOUND':
      // Добавляем новый груз в список
      appState.recentLoads.unshift(message.data);
      
      // Ограничиваем список 10 элементами
      if (appState.recentLoads.length > 10) {
        appState.recentLoads = appState.recentLoads.slice(0, 10);
      }
      
      // Сохраняем в local storage
      chrome.storage.local.set({ recentLoads: appState.recentLoads });
      
      // Обновляем UI
      updateRecentLoads();
      break;
      
    case 'MONITORING_STATUS_CHANGED':
      appState.isActive = message.isActive;
      appState.isLoggedIn = message.isLoggedIn;
      updateUI();
      break;
  }
  
  return true;
});

console.log('Popup script initialized');
