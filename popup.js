// Popup JavaScript для работы с реальными данными
class PopupController {
  constructor() {
    this.isMonitoring = false;
    this.statistics = {};
    this.settings = {};
    
    this.init();
  }
  
  async init() {
    await this.loadData();
    this.setupEventListeners();
    this.updateUI();
    
    // Обновляем данные каждые 2 секунды
    setInterval(() => {
      this.updateUI();
    }, 2000);
  }
  
  async loadData() {
    // Загружаем реальные данные из storage
    const result = await chrome.storage.local.get(['isMonitoring', 'statistics', 'settings']);
    this.isMonitoring = result.isMonitoring || false;
    this.statistics = result.statistics || {
      totalLoadsFound: 0,
      profitableLoadsFound: 0,
      lastScanTime: null,
      monitoringStartTime: null
    };
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
  }
  
  setupEventListeners() {
    document.getElementById('startBtn').addEventListener('click', () => {
      this.toggleMonitoring();
    });
    
    document.getElementById('settingsBtn').addEventListener('click', () => {
      chrome.runtime.openOptionsPage();
    });
  }
  
  async toggleMonitoring() {
    // Получаем активную вкладку с FreightPower
    const tabs = await chrome.tabs.query({ 
      url: 'https://freightpower.schneider.com/*',
      active: true 
    });
    
    if (tabs.length === 0) {
      this.showMessage('Откройте FreightPower для запуска мониторинга');
      return;
    }
    
    const tab = tabs[0];
    
    if (this.isMonitoring) {
      // Останавливаем мониторинг
      await chrome.tabs.sendMessage(tab.id, { type: 'STOP_MONITORING' });
      this.isMonitoring = false;
      await chrome.storage.local.set({ isMonitoring: false });
    } else {
      // Запускаем мониторинг
      await chrome.tabs.sendMessage(tab.id, { type: 'START_MONITORING' });
      this.isMonitoring = true;
      await chrome.storage.local.set({ isMonitoring: true });
    }
    
    this.updateUI();
  }
  
  async updateUI() {
    await this.loadData();
    
    // Обновляем статус
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    
    if (this.isMonitoring) {
      statusDot.classList.add('active');
      statusText.textContent = 'Мониторинг активен';
    } else {
      statusDot.classList.remove('active');
      statusText.textContent = 'Мониторинг остановлен';
    }
    
    // Обновляем статистику
    document.getElementById('totalLoads').textContent = this.statistics.totalLoadsFound || 0;
    document.getElementById('profitableLoads').textContent = this.statistics.profitableLoadsFound || 0;
    
    // Обновляем настройки
    document.getElementById('minRate').textContent = `$${this.settings.minRatePerMile}`;
    document.getElementById('maxDeadhead').textContent = `${this.settings.maxDeadhead} миль`;
    document.getElementById('minDistance').textContent = `${this.settings.minDistance} миль`;
    
    // Обновляем время последнего сканирования
    const lastScanElement = document.getElementById('lastScan');
    if (this.statistics.lastScanTime) {
      const lastScanDate = new Date(this.statistics.lastScanTime);
      const timeDiff = Date.now() - this.statistics.lastScanTime;
      const minutes = Math.floor(timeDiff / 60000);
      
      if (minutes < 1) {
        lastScanElement.textContent = 'Последнее сканирование: только что';
      } else if (minutes < 60) {
        lastScanElement.textContent = `Последнее сканирование: ${minutes} мин назад`;
      } else {
        const hours = Math.floor(minutes / 60);
        lastScanElement.textContent = `Последнее сканирование: ${hours} ч назад`;
      }
    } else {
      lastScanElement.textContent = 'Последнее сканирование: никогда';
    }
    
    // Обновляем кнопку
    const startBtn = document.getElementById('startBtn');
    if (this.isMonitoring) {
      startBtn.textContent = 'Остановить';
      startBtn.className = 'btn btn-danger';
    } else {
      startBtn.textContent = 'Запустить';
      startBtn.className = 'btn btn-primary';
    }
  }
  
  showMessage(message) {
    // Показываем временное сообщение
    const messageDiv = document.createElement('div');
    messageDiv.style.cssText = `
      position: fixed;
      top: 10px;
      left: 50%;
      transform: translateX(-50%);
      background: rgba(0, 0, 0, 0.8);
      color: white;
      padding: 8px 12px;
      border-radius: 4px;
      font-size: 12px;
      z-index: 1000;
    `;
    messageDiv.textContent = message;
    
    document.body.appendChild(messageDiv);
    
    setTimeout(() => {
      document.body.removeChild(messageDiv);
    }, 3000);
  }
}

// Инициализация popup
document.addEventListener('DOMContentLoaded', () => {
  new PopupController();
});
