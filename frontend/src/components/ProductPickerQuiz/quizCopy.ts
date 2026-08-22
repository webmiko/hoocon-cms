import type { QuizAnswers, QuizStepId } from "./quizEngine";
import { estimateRequiredMomentNm } from "./quizMomentEstimate";

export type QuizChoice = {
  id: string;
  title: string;
  hint: string;
};

export type QuizStepCopy = {
  id: QuizStepId;
  question: string;
  lead?: string;
  choices: QuizChoice[];
  skippable?: boolean;
};

const SKIP_VOLTAGE: QuizChoice = {
  id: "skip",
  title: "Пока не знаю",
  hint: "Покажем всю категорию — напряжение выберете в каталоге",
};

const SKIP_CONTROL: QuizChoice = {
  id: "skip",
  title: "Пока не знаю",
  hint: "Покажем категорию — тип управления можно уточнить с инженером",
};

const SKIP_DAMPER: QuizChoice = {
  id: "skip",
  title: "Пока не знаю",
  hint: "Откроем категорию — расчёт момента можно сделать с инженером",
};

export const QUIZ_STEPS: Record<QuizStepId, QuizStepCopy> = {
  need: {
    id: "need",
    question: "Что вам нужно?",
    lead: "Выберите тип продукции — дальше уточним параметры под ваш объект.",
    choices: [
      {
        id: "actuator",
        title: "Привод на заслонку или клапан",
        hint: "Вентиляция, кондиционирование, ОЗК, дымоудаление",
      },
      {
        id: "ball_valve",
        title: "Шаровой кран",
        hint: "Арматура без привода в комплекте",
      },
      {
        id: "kit",
        title: "Комплект кран + привод",
        hint: "Согласованная связка для монтажа",
      },
      {
        id: "adapter",
        title: "Кронштейн на шаровой кран",
        hint: "BR-M или BR-ML — только под приводы Hoocon DA",
      },
    ],
  },
  application: {
    id: "application",
    question: "Где будет работать привод?",
    lead: "От этого зависит серия в каталоге.",
    choices: [
      {
        id: "general",
        title: "Обычная вентиляция и кондиционирование",
        hint: "Приточно-вытяжные системы, фанкойлы, центральные AHU",
      },
      {
        id: "fire",
        title: "Огнезадерживающий клапан (ОЗК)",
        hint: "Серия SA…FU — пружинный возврат, термодатчик DST",
      },
      {
        id: "smoke",
        title: "Дымоудаление",
        hint: "SA…MU без пружины и HVD-…F с пружинным возвратом",
      },
      {
        id: "failsafe",
        title: "Возврат при отключении питания",
        hint: "Обычные воздушные заслонки: пружина FU или электронный QX",
      },
      {
        id: "fast",
        title: "Быстрый ход заслонки",
        hint: "Когда важна скорость открытия и закрытия",
      },
    ],
  },
  failsafe_type: {
    id: "failsafe_type",
    question: "Какой тип возврата?",
    lead: "При пропадании питания клапан должен занять безопасное положение.",
    choices: [
      {
        id: "spring",
        title: "Пружинный возврат (FU)",
        hint: "Механическая пружина — серия DA…FU на воздух",
      },
      {
        id: "electronic",
        title: "Электронный fail-safe (QX)",
        hint: "Конденсаторный возврат — серии HVA/HVD …QX",
      },
    ],
  },
  smoke_return: {
    id: "smoke_return",
    question: "Нужен пружинный возврат на дымовом клапане?",
    lead:
      "В каталоге дымоудаления две семьи: без пружины (SA…MU) и с пружиной (HVD-…F).",
    choices: [
      {
        id: "no_spring",
        title: "Без пружины",
        hint: "Серия SA…MU — 2-/3-позиционное, без возвратной пружины",
      },
      {
        id: "spring",
        title: "С пружинным возвратом",
        hint: "Серия HVD-…F — компактный пружинный привод",
      },
      {
        id: "skip",
        title: "Пока не знаю",
        hint: "Покажем обе семьи дымоудаления",
      },
    ],
    skippable: true,
  },
  voltage: {
    id: "voltage",
    question: "Какое питание?",
    choices: [
      {
        id: "24",
        title: "24 В от щита",
        hint: "BMS, DDC, низковольтные шкафы",
      },
      {
        id: "230",
        title: "230 В от сети",
        hint: "Прямое подключение к сети на объекте",
      },
      SKIP_VOLTAGE,
    ],
    skippable: true,
  },
  control: {
    id: "control",
    question: "Какое управление нужно?",
    choices: [
      {
        id: "onoff",
        title: "Открыть / закрыть",
        hint: "Дискретные контакты, реле, простой контроллер",
      },
      {
        id: "modulating",
        title: "Плавное регулирование (0…10 В и т.п.)",
        hint: "Пропорциональное управление от АСУ или BMS",
      },
      SKIP_CONTROL,
    ],
    skippable: true,
  },
  aux_switch: {
    id: "aux_switch",
    question: "Нужны сухие контакты положения в щит?",
    lead:
      "Вспомогательные переключатели не управляют заслонкой — " +
      "они сообщают BMS, что клапан открыт или закрыт.",
    choices: [
      {
        id: "yes",
        title: "Да, для сигнализации в BMS",
        hint: "Издания с суффиксом S — DS/AS или HVA…S",
      },
      {
        id: "no",
        title: "Нет, достаточно управления",
        hint: "Базовые издания без вспомогательных переключателей",
      },
      {
        id: "skip",
        title: "Пока не знаю",
        hint: "Покажем все издания категории",
      },
    ],
    skippable: true,
  },
  temp_sensor: {
    id: "temp_sensor",
    question: "Нужен термодатчик SAF72 по паспорту клапана?",
    lead:
      "Термодатчик отключает привод при нагреве выше 72 °C. " +
      "ОЗК (SA…FU): «DST» со датчиком, «DS» без. " +
      "Дымоудаление HVD-…F: «ST» со датчиком, «S» без. " +
      "SA…MU в каталоге — только «DS» (без термодатчика).",
    choices: [
      {
        id: "yes",
        title: "Да, нужен термодатчик SAF72",
        hint: "ОЗК «DST» или дымоудаление HVD «ST»",
      },
      {
        id: "no",
        title: "Нет, без термодатчика",
        hint: "ОЗК «DS», HVD «S» или все SA…MU",
      },
      {
        id: "skip",
        title: "Пока не знаю",
        hint: "Покажем оба варианта — уточните по паспорту клапана",
      },
    ],
    skippable: true,
  },
  damper_area: {
    id: "damper_area",
    question: "Какая площадь прохода заслонки?",
    lead: "Возьмите значение из проекта или чертежа, м².",
    choices: [
      {
        id: "up_to_0_3",
        title: "До 0,3 м²",
        hint: "Малые секции, фанкойлы",
      },
      {
        id: "0_3_0_6",
        title: "0,3–0,6 м²",
        hint: "Типичные секции притока и вытяжки",
      },
      {
        id: "0_6_1_0",
        title: "0,6–1,0 м²",
        hint: "Средние воздушные заслонки, AHU",
      },
      {
        id: "1_0_1_6",
        title: "1,0–1,6 м²",
        hint: "Крупные прямоугольные секции",
      },
      {
        id: "1_6_2_5",
        title: "1,6–2,5 м²",
        hint: "Большие клапаны и воздуховоды",
      },
      {
        id: "2_5_4_0",
        title: "2,5–4,0 м²",
        hint: "Тяжёлые узлы",
      },
      {
        id: "over_4",
        title: "Больше 4 м²",
        hint: "Лучше сверить с паспортом заслонки",
      },
      SKIP_DAMPER,
    ],
    skippable: true,
  },
  damper_type: {
    id: "damper_type",
    question: "Какой тип заслонки?",
    lead: "Конструкция влияет на требуемый крутящий момент.",
    choices: [
      {
        id: "round",
        title: "Круглая",
        hint: "Обычно меньший момент на тот же размер",
      },
      {
        id: "rectangular",
        title: "Прямоугольная",
        hint: "Чаще всего в системах ОВК",
      },
      {
        id: "gate",
        title: "Шиберная / ножевая",
        hint: "Выше сопротивление — нужен больший момент",
      },
      {
        id: "skip",
        title: "Пока не знаю",
        hint: "Посчитаем с запасом, как для прямоугольной",
      },
    ],
    skippable: true,
  },
  damper_pressure: {
    id: "damper_pressure",
    question: "Какое расчётное давление на заслонку?",
    lead: "Значение из проекта, Па. Для ОВК обычно 200–600 Па.",
    choices: [
      {
        id: "low",
        title: "До 300 Па",
        hint: "Низкий перепад",
      },
      {
        id: "medium",
        title: "300–600 Па",
        hint: "Типичная приточно-вытяжная вентиляция",
      },
      {
        id: "high",
        title: "600–1000 Па",
        hint: "Повышенный перепад",
      },
      {
        id: "very_high",
        title: "Больше 1000 Па",
        hint: "Заложим запас по моменту",
      },
      {
        id: "skip",
        title: "Пока не знаю",
        hint: "Примем 450 Па — уточните по паспорту клапана",
      },
    ],
    skippable: true,
  },
  dn: {
    id: "dn",
    question: "Условный проход DN",
    lead: "Диаметр трубопровода из проекта.",
    choices: [
      { id: "15", title: "DN 15", hint: "Малый диаметр" },
      { id: "20", title: "DN 20", hint: "Небольшие линии" },
      { id: "25", title: "DN 25", hint: "Частый выбор на объектах" },
      { id: "32", title: "DN 32", hint: "Средний проход" },
      { id: "40", title: "DN 40", hint: "Увеличенный проход" },
      { id: "50", title: "DN 50", hint: "Крупный проход" },
      {
        id: "skip",
        title: "Пока не знаю",
        hint: "Покажем все шаровые краны серии",
      },
    ],
    skippable: true,
  },
  kvs: {
    id: "kvs",
    question: "Какая нужна пропускная способность Kvs?",
    lead: "Значение из гидравлического расчёта, м³/ч.",
    choices: [
      {
        id: "up_to_2_5",
        title: "До 2,5 м³/ч",
        hint: "Малые контуры, DN 15–20",
      },
      {
        id: "2_5_to_6",
        title: "2,5–6,3 м³/ч",
        hint: "Типичные отверстия на DN 15–20",
      },
      {
        id: "6_to_16",
        title: "6–16 м³/ч",
        hint: "Средние линии, DN 25–32",
      },
      {
        id: "16_to_40",
        title: "16–40 м³/ч",
        hint: "Крупные проходы DN 32–40",
      },
      {
        id: "over_40",
        title: "Больше 40 м³/ч",
        hint: "DN 40–50 и максимальные отверстия",
      },
      {
        id: "skip",
        title: "Пока не знаю",
        hint: "Покажем все Kvs в категории — уточните по расчёту",
      },
    ],
    skippable: true,
  },
  ways: {
    id: "ways",
    question: "Сколько ходов у крана?",
    choices: [
      { id: "2", title: "2-ходовой", hint: "Перекрытие или пропуск" },
      { id: "3", title: "3-ходовой", hint: "Смешение или переключение контуров" },
      {
        id: "skip",
        title: "Пока не знаю",
        hint: "Покажем все типы в категории",
      },
    ],
    skippable: true,
  },
  adapter_type: {
    id: "adapter_type",
    question: "Какой у вас привод Hoocon?",
    lead: "В каталоге два кронштейна — выбор зависит от возвратной пружины.",
    choices: [
      {
        id: "br_m",
        title: "Без возвратной пружины (MU / MQU)",
        hint: "Кронштейн BR-M — DA4MU…DA16MQU, 24/230 В",
      },
      {
        id: "br_ml",
        title: "С возвратной пружиной (FU)",
        hint: "Кронштейн BR-ML — только DA5FU, 24/230 В",
      },
      {
        id: "skip",
        title: "Пока не знаю",
        hint: "Покажем оба кронштейна в каталоге",
      },
    ],
    skippable: true,
  },
};

/** Human-readable chips for the live summary strip. */
export function buildQuizSummaryChips(answers: QuizAnswers): string[] {
  const chips: string[] = [];
  if (answers.need === "actuator") chips.push("Привод");
  if (answers.need === "ball_valve") chips.push("Шаровой кран");
  if (answers.need === "kit") chips.push("Комплект");
  if (answers.need === "adapter") chips.push("Адаптер");

  if (answers.application === "general") chips.push("Вентиляция");
  if (answers.application === "fire") chips.push("ОЗК");
  if (answers.application === "smoke") {
    if (answers.smokeReturn === "spring") {
      chips.push("Дымоудаление · HVD-…F");
    } else if (answers.smokeReturn === "no_spring") {
      chips.push("Дымоудаление · SA…MU");
    } else {
      chips.push("Дымоудаление");
    }
  }
  if (answers.application === "fast") chips.push("Быстрый ход");
  if (answers.application === "failsafe") {
    chips.push(
      answers.failsafeType === "electronic"
        ? "Электронный возврат"
        : "Пружинный возврат",
    );
  }

  if (answers.voltage === "24") chips.push("24 В");
  if (answers.voltage === "230") chips.push("230 В");
  if (answers.control === "onoff") chips.push("Открыть / закрыть");
  if (answers.control === "modulating") chips.push("Плавное регулирование");
  if (answers.auxSwitch === "yes") chips.push("Сухие контакты");
  if (answers.auxSwitch === "no") chips.push("Без всп. переключателей");
  if (answers.tempSensor === "yes") chips.push("Термодатчик SAF72");
  if (answers.tempSensor === "no") chips.push("Без термодатчика");
  if (answers.damperArea && answers.damperArea !== "skip") {
    const step = QUIZ_STEPS.damper_area.choices.find(
      (c) => c.id === answers.damperArea,
    );
    if (step) chips.push(step.title);
  }
  if (answers.damperType === "round") chips.push("Круглая");
  if (answers.damperType === "rectangular") chips.push("Прямоугольная");
  if (answers.damperType === "gate") chips.push("Шиберная");
  if (answers.damperPressure && answers.damperPressure !== "skip") {
    const step = QUIZ_STEPS.damper_pressure.choices.find(
      (c) => c.id === answers.damperPressure,
    );
    if (step) chips.push(step.title);
  }
  const estimatedNm = estimateRequiredMomentNm(answers);
  if (estimatedNm !== null) {
    chips.push(`~${estimatedNm} Нм`);
  }
  if (answers.dn && answers.dn !== "skip") chips.push(`DN ${answers.dn}`);
  if (answers.kvs && answers.kvs !== "skip") {
    const step = QUIZ_STEPS.kvs.choices.find((c) => c.id === answers.kvs);
    if (step) chips.push(step.title);
  }
  if (answers.ways === "2") chips.push("2-ходовой");
  if (answers.ways === "3") chips.push("3-ходовой");
  if (answers.adapterType === "br_m") chips.push("BR-M");
  if (answers.adapterType === "br_ml") chips.push("BR-ML");

  return chips;
}

/** Results heading with correct Russian plural for model count. */
export function formatQuizResultsCount(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) {
    return `Нашли ${count} модель`;
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return `Нашли ${count} модели`;
  }
  return `Нашли ${count} моделей`;
}
