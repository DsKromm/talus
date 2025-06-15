import os
import time
import logging
from web3 import Web3, exceptions
from web3.middleware import geth_poa_middleware
from telegram import Bot
from telegram.error import TelegramError
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('talus_claimer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

class TalusClaimer:
    def __init__(self):
        # Конфигурация из переменных окружения
        self.private_key = os.getenv('PRIVATE_KEY')
        self.telegram_token = os.getenv('TELEGRAM_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.rpc_url = os.getenv('RPC_URL', 'https://rpc.talus.network')
        
        # Адреса контрактов (может потребоваться обновление)
        self.loyalty_contract_address = Web3.to_checksum_address(
            os.getenv('LOYALTY_CONTRACT_ADDRESS', '0x123...')  # Замените на актуальный адрес
        )
        
        # ABI контракта (упрощенный вариант, может потребоваться полный ABI)
        self.loyalty_contract_abi = [
            {
                "inputs": [{"internalType": "address", "name": "user", "type": "address"}],
                "name": "claimDailyReward",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]
        
        # Инициализация Web3
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        # Инициализация Telegram бота
        self.tg_bot = Bot(token=self.telegram_token) if self.telegram_token else None
        
        # Проверка подключения
        if not self.w3.is_connected():
            raise ConnectionError("Не удалось подключиться к RPC узлу")

    def get_wallet_address(self):
        """Получаем адрес кошелька из приватного ключа"""
        account = self.w3.eth.account.from_key(self.private_key)
        return account.address

    def claim_daily_reward(self, retries=3, delay=10):
        """Выполняем клейм ежедневной награды"""
        contract = self.w3.eth.contract(
            address=self.loyalty_contract_address,
            abi=self.loyalty_contract_abi
        )
        
        wallet_address = self.get_wallet_address()
        nonce = self.w3.eth.get_transaction_count(wallet_address)
        
        tx_data = {
            'from': wallet_address,
            'nonce': nonce,
            'gas': 200000,
            'gasPrice': self.w3.eth.gas_price
        }
        
        for attempt in range(retries):
            try:
                # Создаем транзакцию
                tx = contract.functions.claimDailyReward(wallet_address).build_transaction(tx_data)
                
                # Подписываем транзакцию
                signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
                
                # Отправляем транзакцию
                tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                
                # Ждем подтверждения
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                
                if receipt.status == 1:
                    logger.info(f"Успешный клейм! Tx hash: {tx_hash.hex()}")
                    self.send_telegram_notification(
                        f"✅ Ежедневная награда успешно заклеймлена!\n"
                        f"Адрес: {wallet_address}\n"
                        f"Транзакция: {self.get_explorer_url(tx_hash.hex())}"
                    )
                    return True
                else:
                    logger.error(f"Транзакция не удалась. Tx hash: {tx_hash.hex()}")
                    raise Exception("Транзакция не удалась")
                    
            except exceptions.ContractLogicError as e:
                error_msg = f"Ошибка контракта: {str(e)}"
                logger.error(error_msg)
                self.send_telegram_notification(f"❌ Ошибка при клейме: {error_msg}")
                return False
                
            except Exception as e:
                logger.error(f"Попытка {attempt + 1} из {retries} не удалась: {str(e)}")
                if attempt < retries - 1:
                    time.sleep(delay)
                else:
                    self.send_telegram_notification(
                        f"❌ Не удалось заклеймить награду после {retries} попыток.\n"
                        f"Ошибка: {str(e)}"
                    )
                    return False
        return False

    def get_explorer_url(self, tx_hash):
        """Возвращает URL транзакции в эксплорере (если доступно)"""
        return f"https://explorer.talus.network/tx/{tx_hash}"

    def send_telegram_notification(self, message):
        """Отправляем уведомление в Telegram"""
        if not self.tg_bot:
            logger.warning("Telegram бот не настроен, уведомления не отправляются")
            return
            
        try:
            self.tg_bot.send_message(chat_id=self.telegram_chat_id, text=message)
            logger.info("Уведомление в Telegram отправлено")
        except TelegramError as e:
            logger.error(f"Ошибка при отправке уведомления в Telegram: {str(e)}")

    def run(self):
        """Основной метод запуска бота"""
        try:
            wallet_address = self.get_wallet_address()
            logger.info(f"Запуск бота для адреса: {wallet_address}")
            
            self.send_telegram_notification(
                f"������ Бот Talus Claimer запущен\n"
                f"Адрес кошелька: {wallet_address}"
            )
            
            # Выполняем клейм
            success = self.claim_daily_reward()
            
            if success:
                logger.info("Бот успешно завершил работу")
            else:
                logger.error("Бот завершил работу с ошибками")
                
        except Exception as e:
            logger.error(f"Критическая ошибка: {str(e)}")
            self.send_telegram_notification(f"������ Критическая ошибка в боте: {str(e)}")
            raise


if __name__ == "__main__":
    try:
        claimer = TalusClaimer()
        claimer.run()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {str(e)}")