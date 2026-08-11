"""Seed / refresh site copy for CMS pages, article excerpts, and news.

Spec: ЕДИНЫЙ_ПРОМПТ_ВЕБ_РАЗРАБОТКИ §6 (конкретика, без штампов), §9.6;
docs/seo-url-migration.md (canonical: /company, /gde-kupit, /oferta,
/privacy-policy, /terms); 152-ФЗ для B2B-лидов.

Usage::

    poetry run python manage.py seed_site_content
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.utils import timezone

from config.warranty import WARRANTY_COMPANY_LI
from content.models import Article, News, Page

_PHONE = "8 800 350-58-98"
_EMAIL_SALES = "sales@hoocon.ru"
_EMAIL_INFO = "info@hoocon.ru"
_HOURS = "Пн–Пт 9:30–17:30 (МСК), сб–вс — выходной"
_ADDRESS = "143440, Московская область, г. о. Красногорск, пгт Путилково, тер. Гринвуд, стр. 7, помещ. 98 (3-й этаж)"
_INN = "5024199634"
_KPP = "502401001"
_OGRN = "1195081070986"
_BANK = "р/с 40702810838000199148, к/с 30101810400000000225, БИК 044525225, ПАО Сбербанк"

# ── Pages (canonical slugs = Tilda sitemap) ───────────────────────────

PAGES: dict[str, tuple[str, str]] = {
    "company": (
        "О компании Hoocon",
        f"""
<p>Hoocon производит электроприводы для систем отопления, вентиляции и
кондиционирования (ОВК). Офис и склад в Московской области — поставки по РФ
напрямую, без публичного прайса: готовим КП под спецификацию и объём.</p>
<p>Бренд работает с 1998 года. В России продукцию представляет
ООО «Хогон». Завод-изготовитель — Ningbo Hoocon Automation Control Equipment
Co., Ltd. (Китай).</p>
<h2>Что поставляем</h2>
<ul>
<li>Приводы воздушных заслонок — регулирование потока в вентиляции.</li>
<li>Приводы противопожарных клапанов и клапанов дымоудаления —
для систем ПБ.</li>
<li>Приводы запорно-регулирующей арматуры и шаровых кранов DN15–DN150 —
теплоноситель и хладагент.</li>
</ul>
<h2>Документы и качество</h2>
<ul>
<li>Система менеджмента качества ISO 9001:2015 (CQC).</li>
<li>Сертификаты CE, UL, BV и российские сертификаты соответствия —
файлы в карточке SKU.</li>
<li>{WARRANTY_COMPANY_LI}</li>
<li>Ответ на заявку — до 2 рабочих часов в рабочие дни.</li>
</ul>
<h2>Как заказать</h2>
<ol>
<li>Подберите модель в <a href="/catalog">каталоге</a> или опишите задачу.</li>
<li>Скачайте паспорт и сертификаты из карточки товара.</li>
<li>Оставьте <a href="/consultation">заявку на КП</a> или позвоните
{_PHONE}.</li>
</ol>
<p>Партнёры и розница: <a href="/gde-kupit">где купить</a>.
OEM и завод: <a href="/zavod">/zavod</a> · {_EMAIL_INFO}.</p>
<h2>Контакты ООО «Хогон»</h2>
<ul>
<li>Телефон: <a href="tel:+78003505898">{_PHONE}</a></li>
<li>Продажи: <a href="mailto:{_EMAIL_SALES}">{_EMAIL_SALES}</a></li>
<li>Сотрудничество: <a href="mailto:{_EMAIL_INFO}">{_EMAIL_INFO}</a></li>
<li>Адрес: {_ADDRESS}</li>
<li>Режим: {_HOURS}</li>
<li>ИНН {_INN}, КПП {_KPP}, ОГРН {_OGRN}</li>
<li>{_BANK}</li>
</ul>
""".strip(),
    ),
    "gde-kupit": (
        "Где купить продукцию Hoocon",
        f"""
<p>Юридические лица могут заказать приводы напрямую у ООО «Хогон»
(склад в Московской области) или у региональных партнёров. Физическим лицам
удобнее обратиться к партнёру в своём городе.</p>
<h2>Прямые поставки (B2B)</h2>
<p>Телефон <a href="tel:+78003505898">{_PHONE}</a>, email
<a href="mailto:{_EMAIL_SALES}">{_EMAIL_SALES}</a>.
<a href="/consultation">Запросить КП</a> — ответим до 2 рабочих часов.</p>
<h2>Представительство завода в Беларуси</h2>
<h3>ООО «Чемпион-Тэк» — Минск</h3>
<ul>
<li>Юридический адрес: 220030 Минск, пр-т Независимости 32А, пом.&nbsp;11</li>
<li>Многоканальный телефон:
<a href="tel:+375293726888">+375 29 372 6888</a></li>
<li>По вопросам сотрудничества:
<a href="mailto:ichampiontech@yandex.ru">ichampiontech@yandex.ru</a></li>
</ul>
<h2>Партнёры</h2>
<h3>«ТД Панорамавент» — Москва</h3>
<ul>
<li>ул. Производственная, д. 11, стр. 6</li>
<li>+7 (495) 380-06-76, info@panoramavent.ru</li>
<li>Пн–Пт 9:00–19:00</li>
</ul>
<h3>ООО «Аэро Групп» — Москва</h3>
<ul>
<li>ул. Электрозаводская, д. 24, офис 306</li>
<li>+7 (495) 780-31-41, office@aerostarmsk.ru</li>
<li><a href="https://www.aerogrupp.ru" rel="noopener noreferrer"
target="_blank">aerogrupp.ru</a>, Telegram @aerogrupp</li>
<li>Пн–Пт 9:00–18:00</li>
</ul>
<h3>ООО «Смарт Альянс» — Санкт-Петербург</h3>
<ul>
<li>Офис: ул. Мельничная, д. 16, корп. 1, этаж 3</li>
<li>Склад: ул. Мельничная, д. 11</li>
<li>8 (800) 333-28-19,
<a href="https://www.hoocon.spb.ru" rel="noopener noreferrer"
target="_blank">hoocon.spb.ru</a></li>
<li>Пн–Пт 10:00–17:00</li>
</ul>
<h3>ООО «РосАвтоматизация» — Минск</h3>
<ul>
<li>ул. Мележа, 1</li>
<li>+375 29 697-11-02, mail.sensorica.by@gmail.com</li>
<li><a href="https://www.hoocon.by" rel="noopener noreferrer"
target="_blank">hoocon.by</a></li>
</ul>
<h2>OEM под своим брендом</h2>
<p>Завод Ningbo Hoocon Automation Control Equipment Co., Ltd.:
OEM-поставки, CE / UL / EAC. Подробнее — на странице
<a href="/zavod">завода и OEM</a>. Запросы —
<a href="mailto:{_EMAIL_INFO}">{_EMAIL_INFO}</a> или
hoocon@hoocon.com.cn.</p>
""".strip(),
    ),
    "zavod": (
        "Заказ приводов ОВК под своим брендом",
        (Path(__file__).resolve().parents[2] / "fixtures" / "page_zavod.html").read_text(
            encoding="utf-8",
        ),
    ),
    "faq": (
        "Ответы на частые вопросы",
        """
<p>Краткие ответы для инженеров и снабжения: расчёт, совместимость серий,
подбор момента. Нужен расчёт под объект —
<a href="/consultation">оставьте заявку</a>.</p>
<h2>Как рассчитать площадь сечения круглого клапана?</h2>
<p>Для диаметра 20 см (0,2 м): радиус 0,1 м,
S = π × r² ≈ 3,14 × 0,01 = 0,0314 м². Всегда переводите размеры в метры.
Площадь сечения задаёт пропускную способность в расчётах вентиляции и ПБ.</p>
<h2>Можно ли заменить SA10FU230-DS на DA10FU230-DS?</h2>
<p><strong>Нет.</strong> SA — для огнезадерживающих клапанов (НО ОЗК):
пружина закрывает заслонку за ≤ 25 с без питания, серия испытана на работу
при высоких температуре и влажности. DA — для общеобменной вентиляции,
эти параметры не нормированы. Замена нарушает требования пожарной
безопасности. Для ОЗК используйте серию SA или сертифицированный аналог.</p>
<h2>Как оценить нужный крутящий момент?</h2>
<p>Учитывайте давление в системе (Па), тип и конструкцию заслонки, условия
среды. Ориентир: M ≈ (D³ × P × k) / C, где D — диаметр или большая сторона (м),
P — давление (Па), k — коэффициент типа заслонки (примерно 0,5–3,0),
C — эмпирический коэффициент (часто 2000–4000). Для проекта сверяйте
таблицы производителя заслонки и паспорт привода в
<a href="/catalog">каталоге</a>.</p>
<h2 id="signal-ma-special-order">Что значит 0(4)...20 мА (спецзаказ)?</h2>
<p>Заводская установка пропорциональных приводов — сигнал напряжения
<strong>0(2)...10 В=</strong> (по умолчанию 0...10 В=). Режим тока
<strong>0(4)...20 мА</strong> доступен только по спецзаказу: переключение
DIP / заводская конфигурация под ваш контроллер. Укажите требование к
току в <a href="/consultation">заявке на КП</a> — менеджер уточнит срок
и исполнение.</p>
<h2 id="fail-safe">Что такое fail-safe у привода?</h2>
<p><strong>Fail-safe</strong> (аварийный возврат) — при пропадании питания
привод сам уводит заслонку в безопасное положение. <strong>FU</strong> —
пружиной (механический возврат), <strong>EU</strong> — электронной схемой
без пружины. Без fail-safe привод остаётся в текущем положении.
Свод по семействам —
<a href="/statyi/spetsifikatsiya-modelnogo-ryada-privodov">в спецификации
модельного ряда</a>.</p>
""".strip(),
    ),
    "kontakty": (
        "Контакты",
        f"""
<p>ООО «Хогон» (бренд Hoocon). Ответим до 2 рабочих часов в рабочие дни.</p>
<ul>
<li><strong>Телефон:</strong>
<a href="tel:+78003505898">{_PHONE}</a></li>
<li><strong>Продажи:</strong>
<a href="mailto:{_EMAIL_SALES}">{_EMAIL_SALES}</a></li>
<li><strong>Сотрудничество / ПДн:</strong>
<a href="mailto:{_EMAIL_INFO}">{_EMAIL_INFO}</a></li>
<li><strong>Адрес:</strong> {_ADDRESS}</li>
<li><strong>Режим:</strong> {_HOURS}</li>
</ul>
<h2>Реквизиты</h2>
<ul>
<li>ИНН {_INN}, КПП {_KPP}, ОГРН {_OGRN}</li>
<li>{_BANK}</li>
</ul>
<h2>Заявка с сайта</h2>
<p><a href="/consultation">Консультация и КП</a>,
<a href="/replacement">подбор аналога Belimo</a>,
<a href="/gde-kupit">где купить</a>.</p>
<p><a href="/privacy-policy">Политика конфиденциальности</a> ·
<a href="/terms">Согласие на обработку ПДн</a> ·
<a href="/oferta">Договор оферты</a></p>
""".strip(),
    ),
    "oferta": (
        "Публичная оферта",
        f"""
<p>Публичная оферта ООО «Хогон» от 01.06.2025. Адресована
<strong>юридическим лицам</strong>. Акцепт — полная оплата по счёту.</p>
<h2>1. Продавец</h2>
<p>ООО «Хогон», {_ADDRESS}, ИНН {_INN}, КПП {_KPP}, ОГРН {_OGRN}.</p>
<h2>2. Покупатель</h2>
<p>Оферта адресована исключительно юридическим лицам (B2B).</p>
<h2>3. Товар</h2>
<p>Исполнительное оборудование систем ОВК. Номенклатура, количество,
цена и сроки — в счёте на оплату, выставленном продавцом.</p>
<h2>4. Акцепт</h2>
<p>Акцептом считается полная оплата по счёту после поступления средств
на расчётный счёт ООО «Хогон». До оплаты счёт не создаёт обязательств
по отгрузке.</p>
<h2>5. Обязанности сторон</h2>
<p>Продавец: передать товар по условиям счёта, надлежащего качества.
Покупатель: оплатить счёт в срок и принять товар.</p>
<h2>6. Поставка</h2>
<p>Адрес поставки — указанный покупателем при заказе. Срок отгрузки —
в течение 7 рабочих дней с даты поступления оплаты, если иное не указано
в счёте (наличие на складе / под заказ).</p>
<h2>7. Возврат</h2>
<p>Возврат некачественного товара — по законодательству РФ при сохранении
упаковки и сопроводительных документов, если иное не согласовано письменно.</p>
<h2>8. Изменения</h2>
<p>Актуальная редакция размещается на сайте. Существенные изменения условий
по уже акцептованному счёту согласуются отдельно.</p>
<h2>9. Прочее</h2>
<p>Оферта действует с момента публикации на сайте. Вопросы, не урегулированные
офертой, регулирует законодательство РФ.</p>
<p>Материалы сайта носят справочный характер и <strong>не являются</strong>
публичной офертой в смысле ст. 437 ГК РФ, за исключением настоящего текста
и счёта на оплату.</p>
""".strip(),
    ),
    "privacy-policy": (
        "Политика обработки персональных данных",
        f"""
<p>Настоящая Политика определяет порядок обработки персональных данных
ООО «Хогон» (далее — Оператор) на сайте <strong>hoocon.ru</strong>
и соответствует Федеральному закону от 27.07.2006 №&nbsp;152-ФЗ
«О персональных данных» (в ред., действующей с 01.09.2025, включая требования
к отдельному оформлению согласия — ст.&nbsp;9), Федеральному закону
от 27.07.2006 №&nbsp;149-ФЗ «Об информации, информационных технологиях
и о защите информации», а также рекомендациям Роскомнадзора для
операторов сайтов.</p>
<p>Сайт ориентирован на B2B: заявки представителей юридических лиц
на подбор, консультацию и поставку оборудования ОВК. Политика доступна
неограниченному кругу лиц (ссылка в подвале сайта).</p>

<h2>1. Оператор персональных данных</h2>
<p><strong>ООО «Хогон»</strong><br>
ИНН {_INN}, КПП {_KPP}, ОГРН {_OGRN}<br>
Адрес: {_ADDRESS}<br>
Тел.: {_PHONE}<br>
Email по вопросам ПДн: <a href="mailto:{_EMAIL_INFO}">{_EMAIL_INFO}</a><br>
Email отдела продаж: <a href="mailto:{_EMAIL_SALES}">{_EMAIL_SALES}</a></p>
<p>Оператор обеспечивает актуальность уведомления об обработке персональных
данных в Роскомнадзоре (ст.&nbsp;22 152-ФЗ) в объёме, предусмотренном законом.</p>

<h2>2. Категории субъектов и состав данных</h2>
<p><strong>2.1. Заявители (формы КП, консультации, подбора аналога)</strong></p>
<ul>
<li>имя, должность (если указаны);</li>
<li>телефон, адрес электронной почты;</li>
<li>название организации и иные сведения, сообщённые в заявке;</li>
<li>содержание запроса: артикул, код Belimo / аналог, количество, ТТХ.</li>
</ul>
<p><strong>2.2. Посетители сайта (технические данные)</strong></p>
<ul>
<li>IP-адрес, User-Agent, дата и время обращения — в объёме, необходимом
для защиты форм (антибот, CSRF) и обеспечения безопасности;</li>
<li>сведения о выборе категорий cookie (см.&nbsp;разд.&nbsp;8) — локально
в браузере пользователя.</li>
</ul>
<p>Специальные категории ПДн, биометрию и данные несовершеннолетних
Оператор через сайт не запрашивает и не обрабатывает целенаправленно.</p>

<h2>3. Цели обработки</h2>
<ul>
<li>рассмотрение заявки, подготовка коммерческого предложения, связь
с представителем организации;</li>
<li>преддоговорные действия и исполнение договора поставки;</li>
<li>техническая консультация по подбору электроприводов и арматуры ОВК;</li>
<li>обеспечение работоспособности и безопасности сайта;</li>
<li>статистика посещений — <strong>только</strong> при отдельном согласии
на аналитические cookie (разд.&nbsp;8);</li>
<li>исполнение обязанностей, установленных законодательством РФ.</li>
</ul>
<p>Рекламные и маркетинговые рассылки без отдельного явного согласия
не осуществляем. Согласие на cookie и согласие на обработку ПДн из форм —
<strong>разные</strong> действия (см. ст.&nbsp;9 152-ФЗ).</p>

<h2>4. Правовые основания</h2>
<ul>
<li>п.&nbsp;5 ч.&nbsp;1 ст.&nbsp;6 152-ФЗ — заключение / исполнение договора,
стороной которого является субъект ПДн, либо преддоговорные действия
по его запросу (заявка на КП);</li>
<li>п.&nbsp;1 ч.&nbsp;1 ст.&nbsp;6 152-ФЗ — согласие субъекта, оформленное
<strong>отдельно</strong> от оферты и иных документов
(страница <a href="/terms">«Согласие на обработку персональных данных»</a>,
чекбокс в форме заявки);</li>
<li>п.&nbsp;2 ч.&nbsp;1 ст.&nbsp;6 152-ФЗ — исполнение обязанностей Оператора
по закону;</li>
<li>для аналитических cookie — отдельное согласие через баннер /
настройки cookie (разд.&nbsp;8).</li>
</ul>

<h2>5. Способы и действия с данными</h2>
<p>Обработка — автоматизированная и неавтоматизированная: сбор, запись,
систематизация, накопление, хранение, уточнение, использование,
передача поручителям (хостинг, SMTP) по договору, удаление / уничтожение.</p>
<p>Профилирование в маркетинговых целях не ведётся. Решений, порождающих
юридические последствия исключительно на основе автоматизированной
обработки, Оператор не принимает.</p>

<h2>6. Хранение, локализация, сроки</h2>
<p>Запись, систематизация, накопление и хранение ПДн граждан РФ при сборе
с использованием сайта осуществляются с использованием баз данных,
находящихся на территории Российской Федерации (ст.&nbsp;18 152-ФЗ),
на инфраструктуре Оператора и привлечённых по поручению провайдеров
(хостинг, почта), расположенных в РФ.</p>
<p>Срок хранения: до достижения целей обработки либо до отзыва согласия —
если нет иных оснований (в т.&nbsp;ч. сроки хранения документов
по договорам — ориентир до 5 лет по требованиям бухгалтерского
и налогового учёта / исковой давности).</p>

<h2>7. Передача третьим лицам и трансграничная передача</h2>
<p>ПДн не продаём и не передаём для самостоятельного маркетинга третьих лиц.</p>
<p>Возможна передача:</p>
<ul>
<li>провайдерам хостинга и SMTP — по поручению Оператора
(ст.&nbsp;6 152-ФЗ), в объёме, нужном для работы сайта и доставки писем;</li>
<li>логистическим партнёрам — для исполнения поставки по договору;</li>
<li>госорганам — в случаях, предусмотренных законом РФ.</li>
</ul>
<p>При согласии на аналитические cookie могут использоваться сервисы
<strong>Яндекс.Метрика</strong> (ООО «Яндекс», РФ) и, если подключены
на сайте, <strong>Google Analytics 4</strong> (Google LLC). Передача
в Метрику осуществляется в соответствии с условиями Яндекса.
При использовании GA4 возможна трансграничная передача технических
данных в страны, где расположены серверы Google; такая передача
выполняется <strong>только после вашего явного согласия</strong>
на категорию «Аналитика» в настройках cookie. Отказаться можно в любой
момент (разд.&nbsp;8).</p>

<h2>8. Cookie и аналогичные технологии</h2>
<p>На сайте используются файлы cookie и локальное хранилище браузера
(<code>localStorage</code>). Это не смешивается с согласием на обработку
ПДн из форм заявки.</p>
<p><strong>8.1. Обязательные (всегда активны)</strong> — необходимы
для работы сайта и не отключаются в баннере:</p>
<ul>
<li>защита форм и CSRF (сессионные / служебные cookie Django);</li>
<li>хранение вашего выбора категорий cookie в браузере
(ключ <code>hoocon-cookie-consent</code> в <code>localStorage</code>);</li>
<li>служебные параметры интерфейса (например, тема оформления —
ключ <code>hoocon-theme</code>), не относящиеся к аналитике.</li>
</ul>
<p><strong>8.2. Аналитические (необязательные)</strong> — Яндекс.Метрика
и/или Google Analytics 4. Скрипты аналитики <strong>не загружаются</strong>,
пока вы явно не разрешите категорию «Аналитика»:</p>
<ul>
<li>кнопка «Принять все» в баннере при первом визите; или</li>
<li>включение переключателя в панели «Настроить» / «Настройки cookie»;
панель открывается из подвала сайта в любой момент.</li>
</ul>
<p>Варианты «Только обязательные» и снятие согласия на аналитику
означают отказ от необязательных cookie: счётчики аналитики
не подключаются (или перестают подключаться при следующих загрузках
страницы). Рекламные cookie на сайте не используем.</p>
<p>Подробное управление: подвал сайта → «Настройки cookie».</p>

<h2>9. Права субъекта персональных данных</h2>
<p>Вы вправе запросить доступ, уточнение, блокирование, удаление ПДн,
отозвать согласие, а также обжаловать действия Оператора — в порядке
ст.&nbsp;14–17 152-ФЗ.</p>
<p>Запрос: на <a href="mailto:{_EMAIL_INFO}">{_EMAIL_INFO}</a>
или письменно по адресу Оператора. Срок ответа — в пределах,
установленных 152-ФЗ. Отзыв согласия не затрагивает обработку,
уже выполненную до отзыва, и обработку, необходимую для исполнения
договора или обязанностей по закону.</p>
<p>Жалоба: Роскомнадзор (rkn.gov.ru).</p>

<h2>10. Меры защиты</h2>
<p>Оператор применяет правовые, организационные и технические меры
(ст.&nbsp;19 152-ФЗ): разграничение доступа, защищённая передача (HTTPS),
ограничение круга лиц, имеющих доступ к заявкам, учёт носителей
и резервное копирование в объёме, соответствующем характеру обработки.</p>

<h2>11. Изменение Политики</h2>
<p>Актуальная редакция всегда публикуется на этой странице. Существенные
изменения доводим путём обновления текста и даты. Продолжение пользования
сайтом после публикации новой редакции означает ознакомление с ней;
для согласий, требующих отдельного волеизъявления (формы, аналитика),
сохраняются механизмы, описанные в разд.&nbsp;4 и&nbsp;8.</p>
<p>Дата актуализации: 20 июля 2026 г.</p>
""".strip(),
    ),
    "terms": (
        "Согласие на обработку персональных данных",
        f"""
<p>Настоящий документ является <strong>отдельным согласием</strong>
на обработку персональных данных в смысле ст.&nbsp;9 Федерального закона
от 27.07.2006 №&nbsp;152-ФЗ (в ред., действующей с 01.09.2025) и
<strong>не входит</strong> в текст публичной оферты, пользовательского
соглашения или иных документов, акцептуемых на сайте.</p>
<p>Направляя заявку на сайте hoocon.ru и отмечая согласие в форме,
вы как представитель организации даёте ООО «Хогон»
(ИНН {_INN}, ОГРН {_OGRN}, адрес: {_ADDRESS}) согласие
на обработку персональных данных на условиях ниже.</p>
<h2>Состав данных</h2>
<ul>
<li>ФИО, должность;</li>
<li>телефон, email;</li>
<li>название и реквизиты организации (если сообщите);</li>
<li>содержание заявки (артикул, ТТХ, количество, аналог Belimo).</li>
</ul>
<h2>Цели</h2>
<ul>
<li>заключение и исполнение договоров поставки;</li>
<li>консультации и направление коммерческого предложения;</li>
<li>связь по заявке (email, телефон).</li>
</ul>
<h2>Способы и срок</h2>
<p>Автоматизированная и неавтоматизированная обработка: сбор, запись,
систематизация, хранение, уточнение, использование, удаление.
Хранение — с использованием баз данных на территории РФ.
Срок — до достижения целей или отзыва согласия, но не менее сроков,
установленных законом для договорных отношений (ориентир 5 лет).</p>
<h2>Что не покрывает это согласие</h2>
<p>Использование аналитических cookie (Яндекс.Метрика / Google Analytics)
регулируется отдельно — баннером и настройками cookie на сайте.
Отказ от аналитики не препятствует отправке заявки.</p>
<h2>Отзыв</h2>
<p>Письменный запрос на <a href="mailto:{_EMAIL_INFO}">{_EMAIL_INFO}</a>
или письмо на {_ADDRESS}. Отзыв не влияет на обработку, необходимую
для исполнения уже заключённого договора.</p>
<p>Подробности —
<a href="/privacy-policy">политика обработки персональных данных</a>.
Условия поставки —
<a href="/oferta">публичная оферта</a>.</p>
<p>Дата актуализации: 20 июля 2026 г.</p>
""".strip(),
    ),
    # Alias kept for old internal links until 301 in nginx.
    "privacy": (
        "Политика обработки персональных данных",
        '<p>Актуальная редакция перенесена на страницу <a href="/privacy-policy">/privacy-policy</a>.</p>',
    ),
    "o-kompanii": (
        "О компании Hoocon",
        '<p>Актуальная страница — <a href="/company">О компании</a> (/company).</p>',
    ),
}

_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"

ARTICLE_EXCERPTS: dict[str, str] = {
    "hoocon-kompaniya-i-produktsiya": (
        "Технический обзор DA / SA / HV: fail-safe, BLDC, момент 5–20 Нм, "
        "сигналы управления. Завод и OEM — на странице /zavod."
    ),
    "ispolnitelnoe-oborudovanie-ovk": (
        "Какое исполнительное оборудование нужно для ОВК: электроприводы и "
        "шаровые краны Hoocon с CE, UL, EAC — для вентиляции, дымоудаления и "
        "отопления."
    ),
    "primenenie-privodov-v-sistemah-ventilyatsii": (
        "Где ставят электроприводы в вентиляции: расчёт момента, требования "
        "к промышленным, противопожарным и энергоэффективным системам."
    ),
    "protivopozharnye-vs-vzryvozashchishchennye-privody": (
        "Чем отличаются противопожарные и взрывозащищённые приводы ОВК: "
        "когда нужен каждый тип и на что смотреть в спецификации."
    ),
    "spetsifikatsiya-modelnogo-ryada-privodov": (
        "Спецификация модельного ряда приводов вентиляции Hoocon: серии, моменты и типичные задачи подбора."
    ),
    "sharovye-krany-vidy-konstruktsiya": (
        "Шаровые краны: виды, конструкция и комплектация с приводом — как выбрать узел под давление и среду."
    ),
    "ventilyatsiya-v-metro": (
        "Как устроена вентиляция московского метро и какую роль играют приводы клапанов в обновлении воздуха."
    ),
    "ognezaderzhivayushchii-klapan": (
        "Огнезадерживающий клапан: принцип работы и где применяют — роль электропривода в противопожарной вентиляции."
    ),
    "protivopozharnye-vs-dymoudaleniya-privody": (
        "Противопожарные клапаны vs клапаны дымоудаления: какие приводы "
        "нужны и чем отличаются требования к управлению."
    ),
    "sertifikaty-ce-ul-eac-elektroprivody-ovk": (
        "CE, UL и EAC для электроприводов ОВК: допуск и приёмка по региону, "
        "что сверять в карточке SKU и чем знаки не заменяют подбор момента."
    ),
    "podbor-privoda-po-momentu-i-ploshchadi": (
        "Как выбрать электропривод для заслонки: подбор по крутящему моменту "
        "через площадь и давление (ориентир), затем ряд Нм в каталоге."
    ),
    "tipy-upravleniya-privodom": (
        "Типы электроприводов для вентиляции: Открыто/закрыто, 2-/3 и "
        "пропорциональное с сигналом 0(2)…10 В=; мА — спецзаказ."
    ),
    "pitanie-24-ili-230-v": (
        "Электропривод 230 В или 24 В: как выбрать номинал по щиту и АСУ, класс защиты III/II и IP — разные оси."
    ),
    "mu-mqu-hv-kogda-nuzhen-uskorennyy": (
        "MU, MQU и HV: когда скорость хода нужна по ТЗ — и почему ускоренный "
        "привод не заменяет возврат при отключении питания."
    ),
    "analog-belimo-hoocon": (
        "Как подобрать замену Belimo на Hoocon: сверить момент, пружину, "
        "питание и сигнал — и оформить заявку без слепого кросса по артикулу."
    ),
}

# Titles for articles created from fixtures (not only rewritten from Tilda scrape).
ARTICLE_TITLES: dict[str, str] = {
    "sertifikaty-ce-ul-eac-elektroprivody-ovk": "CE, UL и EAC для электроприводов ОВК",
    "podbor-privoda-po-momentu-i-ploshchadi": ("Подбор привода по площади и давлению: как выбрать момент"),
    "tipy-upravleniya-privodom": ("Типы управления приводом: Открыто/закрыто, 2-/3 и 0–10 В"),
    "pitanie-24-ili-230-v": "24 В или 230 В: что выбрать для электропривода",
    "mu-mqu-hv-kogda-nuzhen-uskorennyy": ("MU, MQU и HV: когда скорость хода действительно нужна"),
    "analog-belimo-hoocon": "Замена Belimo на Hoocon: как подбирать аналог",
}

ARTICLE_COVERS: dict[str, Path] = {
    "sertifikaty-ce-ul-eac-elektroprivody-ovk": (_FIXTURES_DIR / "article_sertifikaty_ce_ul_eac_cover_light.webp"),
    "podbor-privoda-po-momentu-i-ploshchadi": (_FIXTURES_DIR / "article_podbor_privoda_cover.webp"),
    "tipy-upravleniya-privodom": (_FIXTURES_DIR / "article_tipy_upravleniya_cover.webp"),
    "pitanie-24-ili-230-v": (_FIXTURES_DIR / "article_pitanie_24_230_cover.webp"),
    "mu-mqu-hv-kogda-nuzhen-uskorennyy": (_FIXTURES_DIR / "article_mu_mqu_hv_cover.webp"),
    "analog-belimo-hoocon": (_FIXTURES_DIR / "article_analog_belimo_cover.webp"),
}

ARTICLE_COVERS_DARK: dict[str, Path] = {
    "sertifikaty-ce-ul-eac-elektroprivody-ovk": (_FIXTURES_DIR / "article_sertifikaty_ce_ul_eac_cover_dark.webp"),
    "podbor-privoda-po-momentu-i-ploshchadi": (_FIXTURES_DIR / "article_podbor_privoda_cover_dark.webp"),
    "tipy-upravleniya-privodom": (_FIXTURES_DIR / "article_tipy_upravleniya_cover_dark.webp"),
    "pitanie-24-ili-230-v": (_FIXTURES_DIR / "article_pitanie_24_230_cover_dark.webp"),
    "mu-mqu-hv-kogda-nuzhen-uskorennyy": (_FIXTURES_DIR / "article_mu_mqu_hv_cover_dark.webp"),
    "analog-belimo-hoocon": (_FIXTURES_DIR / "article_analog_belimo_cover_dark.webp"),
}

# Full body rewrite (replaces Tilda scrape). Excerpt still from ARTICLE_EXCERPTS.
ARTICLE_BODIES: dict[str, Path] = {
    "spetsifikatsiya-modelnogo-ryada-privodov": (_FIXTURES_DIR / "article_spetsifikatsiya_modelnogo_ryada.html"),
    "primenenie-privodov-v-sistemah-ventilyatsii": (_FIXTURES_DIR / "article_primenenie_privodov_ventilyatsii.html"),
    "hoocon-kompaniya-i-produktsiya": (_FIXTURES_DIR / "article_hoocon_company_products.html"),
    "ispolnitelnoe-oborudovanie-ovk": (_FIXTURES_DIR / "article_ispolnitelnoe_oborudovanie_ovk.html"),
    "protivopozharnye-vs-vzryvozashchishchennye-privody": (
        _FIXTURES_DIR / "article_protivopozharnye_vs_vzryvozashchishchennye.html"
    ),
    "protivopozharnye-vs-dymoudaleniya-privody": (_FIXTURES_DIR / "article_protivopozharnye_vs_dymoudaleniya.html"),
    "ognezaderzhivayushchii-klapan": (_FIXTURES_DIR / "article_ognezaderzhivayushchii_klapan.html"),
    "sharovye-krany-vidy-konstruktsiya": (_FIXTURES_DIR / "article_sharovye_krany.html"),
    "ventilyatsiya-v-metro": (_FIXTURES_DIR / "article_ventilyatsiya_v_metro.html"),
    "sertifikaty-ce-ul-eac-elektroprivody-ovk": (_FIXTURES_DIR / "article_sertifikaty_ce_ul_eac.html"),
    "podbor-privoda-po-momentu-i-ploshchadi": (_FIXTURES_DIR / "article_podbor_privoda_po_momentu.html"),
    "tipy-upravleniya-privodom": (_FIXTURES_DIR / "article_tipy_upravleniya_privodom.html"),
    "pitanie-24-ili-230-v": (_FIXTURES_DIR / "article_pitanie_24_ili_230.html"),
    "mu-mqu-hv-kogda-nuzhen-uskorennyy": (_FIXTURES_DIR / "article_mu_mqu_hv.html"),
    "analog-belimo-hoocon": (_FIXTURES_DIR / "article_analog_belimo_hoocon.html"),
}


def _article_publish_schedule() -> dict[str, datetime]:
    """Staggered go-live (Europe/Moscow). Live now: sertifikaty + podbor."""
    msk = ZoneInfo("Europe/Moscow")
    return {
        # Already on site (keep stable go-live for seed rewrites).
        "sertifikaty-ce-ul-eac-elektroprivody-ovk": datetime(2026, 8, 6, 9, 0, tzinfo=msk),
        # Live with news (2026-08-11).
        "podbor-privoda-po-momentu-i-ploshchadi": datetime(2026, 8, 11, 9, 0, tzinfo=msk),
        # Preview locally via CONTENT_SHOW_SCHEDULED; prod waits.
        "tipy-upravleniya-privodom": datetime(2026, 8, 13, 9, 0, tzinfo=msk),
        "pitanie-24-ili-230-v": datetime(2026, 8, 15, 9, 0, tzinfo=msk),
        "mu-mqu-hv-kogda-nuzhen-uskorennyy": datetime(2026, 8, 17, 9, 0, tzinfo=msk),
        "analog-belimo-hoocon": datetime(2026, 8, 19, 9, 0, tzinfo=msk),
    }


_LEAD_MARKER = 'data-hoocon-lead="1"'


def _lead_html(text: str) -> str:
    """Wrap excerpt-style answer as the first body paragraph."""
    return f"<p {_LEAD_MARKER}><strong>{text}</strong></p>\n"


NEWS_BODY = f"""
<p>В каталоге доступен электропривод <strong>HVA-5NM</strong> с крутящим
моментом 5&nbsp;Н·м — для воздушных клапанов и компактных узлов ОВК.</p>
<p>В карточке SKU — паспорт и основные ТТХ. Для расчёта цены и срока
отгрузки оставьте <a href="/consultation">заявку на КП</a> или позвоните
{_PHONE}.</p>
<p><a href="/catalog">Перейти в каталог</a></p>
""".strip()

_NEWS_LAUNCH_SLUG = "launch-hva-5nm"
_NEWS_LAUNCH_TITLE = "В каталоге: электропривод HVA-5NM (5 Н·м)"

_NEWS_H8205_SLUG = "launch-h8205-lav"
_NEWS_H8205_TITLE = "Доступен заказ: регулирующие клапаны H8205-LAV"
_NEWS_H8205_COVER_SKU = "H8205-LAV232-24A"

NEWS_H8205_BODY = f"""
<p>В каталоге открыт заказ линейки <strong>H8205-LAV</strong> — электрических
регулирующих клапанов (серия&nbsp;82) для автоматического управления расходом
среды в системах ОВК и промышленных АСУ&nbsp;ТП.</p>
<p><strong>Применение.</strong> Клапан изменяет степень открытия по сигналу
управления и регулирует расход (температура, уровень, давление) в контурах
отопления, вентиляции и кондиционирования, а также в смежных отраслях:
нефтехимия, металлургия, электроэнергетика, природоохранные системы.</p>
<p><strong>Что в серии.</strong> 2- и 3-ходовые корпуса DN&nbsp;32…300,
фланец PN16/PN25, рабочая среда по умолчанию — холодная и горячая вода
(раствор этиленгликоля ≤ 50&nbsp;% — по спецзаказу),
температура среды –20…+150&nbsp;°C. На карточке — питания 24/230&nbsp;В,
управление открыто/закрыто, пропорциональное или Modbus, опции
вспомогательного переключателя и аварийного сигнала.</p>
<p>Паспорт, габариты и схемы подключения — в карточке комплекта. Для расчёта
цены и срока отгрузки оставьте <a href="/consultation">заявку на КП</a> или
позвоните {_PHONE}.</p>
<p><a href="/catalog/komplekty">Смотреть H8205-LAV в каталоге</a></p>
""".strip()

_NEWS_BR_SLUG = "launch-br-adapters"
_NEWS_BR_TITLE = "В каталоге: адаптеры BR-M и BR-ML для шаровых кранов"
_NEWS_BR_COVER_SKU = "BR-M"

NEWS_BR_BODY = f"""
<p>В каталоге опубликованы адаптеры (кронштейны)
<strong>BR-M</strong> и <strong>BR-ML</strong> — для установки электропривода
на латунные шаровые краны серии&nbsp;8100.</p>
<p><strong>BR-M</strong> — под приводы без возвратной пружины
(DA…MU / DA…MQU, 24/230&nbsp;В). <strong>BR-ML</strong> — под приводы
с пружинным возвратом: только серия <strong>DA5FU</strong>
(24/230&nbsp;В).</p>
<p>На карточках — совместимые семейства приводов, индексы партнёра и
технички PDF (кронштейн и шток). В RFQ для шаровых 8100 кронштейн
подставляется автоматически: <strong>BR-ML</strong> для DA5FU,
иначе <strong>BR-M</strong> (для фланцевых ВЧШГ — BR-H).</p>
<p>Для расчёта цены и срока отгрузки оставьте
<a href="/consultation">заявку на КП</a> или позвоните {_PHONE}.</p>
<p>
  <a href="/catalog/adaptery">Адаптеры в каталоге</a>
  ·
  <a href="/catalog/adaptery/adapter-br-m">BR-M</a>
  ·
  <a href="/catalog/adaptery/adapter-br-ml">BR-ML</a>
</p>
""".strip()

_NEWS_GUIDES_SLUG = "articles-podbor-i-sertifikaty"
_NEWS_GUIDES_TITLE = "Новые статьи: подбор привода и сертификаты CE/UL/EAC"
_NEWS_GUIDES_COVER = _FIXTURES_DIR / "article_podbor_privoda_cover.webp"

NEWS_GUIDES_BODY = """
<p>В разделе <a href="/statyi">«Статьи»</a> — два практических материала для
подбора и приёмки электроприводов ОВК.</p>
<p><strong>Подбор по моменту.</strong>
<a href="/statyi/podbor-privoda-po-momentu-i-ploshchadi">Подбор привода по
площади и давлению</a>: как оценить крутящий момент через площадь и
перепад давления, затем перейти к ряду Н·м в каталоге.</p>
<p><strong>Сертификаты.</strong>
<a href="/statyi/sertifikaty-ce-ul-eac-elektroprivody-ovk">CE, UL и EAC для
электроприводов ОВК</a>: что сверять в карточке SKU по региону поставки и
чем знаки не заменяют расчёт момента.</p>
<p>Остальные гайды серии (типы управления, 24/230&nbsp;В, MU/MQU/HV, аналог
Belimo) выходят по расписанию.</p>
""".strip()

# News from Tilda /news are imported by ``scrape_hoocon_news`` (covers + body).
# Seed creates a bootstrap HVA item when empty and upserts H8205-LAV / BR / guides.


class Command(BaseCommand):
    """Upsert CMS pages, rewrite article excerpts, refresh news body."""

    help = "Seed site copy: pages, article excerpts, news (B2B tone)."

    def handle(self, *args: object, **options: object) -> None:
        """Write canonical copy into the database."""
        from content.article_slug_renames import apply_article_slug_renames
        from content.news_cover_from_sku import attach_sku_cover_to_news
        from content.news_slug_renames import apply_news_slug_renames

        now = timezone.now()
        for old_slug, new_slug in apply_article_slug_renames():
            self.stdout.write(f"article slug: {old_slug} → {new_slug} (+301)")
        for old_slug, new_slug in apply_news_slug_renames():
            self.stdout.write(f"news slug: {old_slug} → {new_slug} (+301)")

        pages_done = 0
        for slug, (title, body) in PAGES.items():
            _, created = Page.objects.update_or_create(
                slug=slug,
                defaults={
                    "title": title,
                    "body": body,
                    "is_published": True,
                    "published_at": now,
                },
            )
            pages_done += 1
            action = "created" if created else "updated"
            self.stdout.write(f"page {slug}: {action}")

        excerpts_done = 0
        bodies_done = 0
        covers_done = 0
        publish_at = _article_publish_schedule()
        for slug, body_path in ARTICLE_BODIES.items():
            article = Article.objects.filter(slug=slug).first()
            body_html = body_path.read_text(encoding="utf-8")
            excerpt = ARTICLE_EXCERPTS.get(slug, "")
            go_live = publish_at.get(slug, now)
            if article is None:
                article_title = ARTICLE_TITLES.get(slug)
                if not article_title:
                    self.stdout.write(self.style.WARNING(f"article missing: {slug}"))
                    continue
                article = Article.objects.create(
                    slug=slug,
                    title=article_title,
                    body=body_html,
                    excerpt=excerpt,
                    is_published=True,
                    published_at=go_live,
                )
                bodies_done += 1
                self.stdout.write(f"article body: {slug} (created, published_at={go_live.isoformat()})")
            else:
                article.body = body_html
                if excerpt:
                    article.excerpt = excerpt
                update_fields = ["excerpt", "body", "updated_at"]
                if slug in ARTICLE_TITLES and article.title != ARTICLE_TITLES[slug]:
                    article.title = ARTICLE_TITLES[slug]
                    update_fields.append("title")
                if slug in publish_at and article.published_at != go_live:
                    article.published_at = go_live
                    update_fields.append("published_at")
                article.save(update_fields=update_fields)
                bodies_done += 1
                self.stdout.write(f"article body: {slug}")

            # Theme covers are always WebP fixtures; re-save so seed refreshes assets.
            cover_path = ARTICLE_COVERS.get(slug)
            if cover_path is not None and cover_path.is_file():
                from django.core.files.base import ContentFile

                article.cover.save(
                    cover_path.name,
                    ContentFile(cover_path.read_bytes()),
                    save=True,
                )
                covers_done += 1
                self.stdout.write(f"article cover (light): {slug}")

            dark_path = ARTICLE_COVERS_DARK.get(slug)
            if dark_path is not None and dark_path.is_file():
                from django.core.files.base import ContentFile

                article.cover_dark.save(
                    dark_path.name,
                    ContentFile(dark_path.read_bytes()),
                    save=True,
                )
                covers_done += 1
                self.stdout.write(f"article cover_dark: {slug}")

        for slug, excerpt in ARTICLE_EXCERPTS.items():
            if slug in ARTICLE_BODIES:
                continue
            article = Article.objects.filter(slug=slug).first()
            if article is None:
                self.stdout.write(self.style.WARNING(f"article missing: {slug}"))
                continue
            article.excerpt = excerpt
            if _LEAD_MARKER not in article.body:
                article.body = _lead_html(excerpt) + article.body
            article.save(update_fields=["excerpt", "body", "updated_at"])
            excerpts_done += 1
            self.stdout.write(f"article: {slug}")

        news_action = "skipped"
        if not News.objects.exists():
            news, news_created = News.objects.update_or_create(
                slug=_NEWS_LAUNCH_SLUG,
                defaults={
                    "title": _NEWS_LAUNCH_TITLE,
                    "body": NEWS_BODY,
                    "is_published": True,
                    "published_at": now,
                },
            )
            news_action = "created" if news_created else "updated"
            self.stdout.write(f"news {news.slug}: {news_action}")
        else:
            self.stdout.write("news: skipped create (use scrape_hoocon_news)")

        h8205, h8205_created = News.objects.update_or_create(
            slug=_NEWS_H8205_SLUG,
            defaults={
                "title": _NEWS_H8205_TITLE,
                "body": NEWS_H8205_BODY,
                "is_published": True,
            },
        )
        if h8205.published_at is None:
            h8205.published_at = now
            h8205.save(update_fields=["published_at", "updated_at"])
        self.stdout.write(f"news {h8205.slug}: {'created' if h8205_created else 'updated'}")

        if attach_sku_cover_to_news(news_slug=_NEWS_LAUNCH_SLUG):
            self.stdout.write(f"news {_NEWS_LAUNCH_SLUG}: cover from HVA230-5")
        else:
            existing = News.objects.filter(slug=_NEWS_LAUNCH_SLUG).first()
            if existing is None:
                self.stdout.write(self.style.WARNING(f"news cover: {_NEWS_LAUNCH_SLUG} missing"))
            elif existing.cover:
                self.stdout.write(f"news {_NEWS_LAUNCH_SLUG}: cover already set")
            else:
                self.stdout.write(self.style.WARNING(f"news {_NEWS_LAUNCH_SLUG}: cover not attached (SKU image?)"))

        if attach_sku_cover_to_news(
            news_slug=_NEWS_H8205_SLUG,
            sku_code=_NEWS_H8205_COVER_SKU,
        ):
            self.stdout.write(f"news {_NEWS_H8205_SLUG}: cover from {_NEWS_H8205_COVER_SKU}")
        elif h8205.cover:
            self.stdout.write(f"news {_NEWS_H8205_SLUG}: cover already set")
        else:
            self.stdout.write(self.style.WARNING(f"news {_NEWS_H8205_SLUG}: cover not attached (SKU image?)"))

        br_news, br_created = News.objects.update_or_create(
            slug=_NEWS_BR_SLUG,
            defaults={
                "title": _NEWS_BR_TITLE,
                "body": NEWS_BR_BODY,
                "is_published": True,
            },
        )
        if br_news.published_at is None:
            br_news.published_at = now
            br_news.save(update_fields=["published_at", "updated_at"])
        self.stdout.write(f"news {br_news.slug}: {'created' if br_created else 'updated'}")

        if attach_sku_cover_to_news(
            news_slug=_NEWS_BR_SLUG,
            sku_code=_NEWS_BR_COVER_SKU,
            force=False,
        ):
            self.stdout.write(f"news {_NEWS_BR_SLUG}: cover from {_NEWS_BR_COVER_SKU}")
        elif br_news.cover:
            self.stdout.write(f"news {_NEWS_BR_SLUG}: cover already set")
        else:
            self.stdout.write(
                self.style.WARNING(f"news {_NEWS_BR_SLUG}: cover not attached (SKU image?)"),
            )

        guides, guides_created = News.objects.update_or_create(
            slug=_NEWS_GUIDES_SLUG,
            defaults={
                "title": _NEWS_GUIDES_TITLE,
                "body": NEWS_GUIDES_BODY,
                "is_published": True,
            },
        )
        if guides.published_at is None:
            guides.published_at = now
            guides.save(update_fields=["published_at", "updated_at"])
        self.stdout.write(f"news {guides.slug}: {'created' if guides_created else 'updated'}")
        if not guides.cover and _NEWS_GUIDES_COVER.is_file():
            from django.core.files.base import ContentFile

            guides.cover.save(
                _NEWS_GUIDES_COVER.name,
                ContentFile(_NEWS_GUIDES_COVER.read_bytes()),
                save=True,
            )
            self.stdout.write(f"news {_NEWS_GUIDES_SLUG}: cover from fixture")
        elif guides.cover:
            self.stdout.write(f"news {_NEWS_GUIDES_SLUG}: cover already set")

        from content.news_categories import assign_news_categories, ensure_categories

        ensure_categories()
        assigned = assign_news_categories()
        self.stdout.write(f"news categories: assigned={assigned}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: pages={pages_done}, article_bodies={bodies_done}, "
                f"article_covers={covers_done}, articles={excerpts_done}, news={news_action}"
            )
        )
