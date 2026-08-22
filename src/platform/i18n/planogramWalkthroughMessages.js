export const PLANOGRAM_WALKTHROUGH_MESSAGES = Object.freeze({
  tr: Object.freeze({
    walk: "Yürüme modu",
    hint: "Sahneye tıklayıp fareyle bak; W/A/S/D ile ilerle, ok tuşlarıyla ilerle ve dön. Duvar, fixture ve yasak alan çarpışmaları hareketi engeller.",
    canvasLabel: "Çarpışma kontrollü birinci şahıs planogram mağaza yürüyüşü",
  }),
  en: Object.freeze({
    walk: "Walk-through",
    hint: "Click the scene to look with the mouse; move with W/A/S/D, and use the arrow keys to move and turn. Walls, fixtures and no-go areas block movement.",
    canvasLabel: "Collision-aware first-person planogram store walk-through",
  }),
  de: Object.freeze({
    walk: "Begehung",
    hint: "Klicken Sie in die Szene und sehen Sie sich mit der Maus um; bewegen Sie sich mit W/A/S/D und nutzen Sie die Pfeiltasten zum Gehen und Drehen. Wände, Fixtures und Sperrflächen blockieren die Bewegung.",
    canvasLabel: "Kollisionsgeprüfte Planogramm-Begehung aus der Ich-Perspektive",
  }),
  ar: Object.freeze({
    walk: "جولة داخل المتجر",
    hint: "انقر داخل المشهد للنظر بالماوس؛ تحرك باستخدام W/A/S/D واستخدم مفاتيح الأسهم للحركة والدوران. تمنع الجدران والتجهيزات والمناطق المحظورة المرور.",
    canvasLabel: "جولة بلانوغرام من منظور الشخص الأول مع كشف التصادم",
  }),
  fr: Object.freeze({
    walk: "Visite immersive",
    hint: "Cliquez dans la scène pour regarder à la souris ; déplacez-vous avec W/A/S/D et utilisez les flèches pour avancer et tourner. Les murs, équipements et zones interdites bloquent le déplacement.",
    canvasLabel: "Visite du planogramme à la première personne avec gestion des collisions",
  }),
  es: Object.freeze({
    walk: "Recorrido",
    hint: "Haz clic en la escena para mirar con el ratón; muévete con W/A/S/D y usa las flechas para avanzar y girar. Las paredes, fixtures y zonas restringidas bloquean el movimiento.",
    canvasLabel: "Recorrido de planograma en primera persona con control de colisiones",
  }),
  it: Object.freeze({
    walk: "Walk-through",
    hint: "Fai clic sulla scena per guardarti intorno con il mouse; muoviti con W/A/S/D e usa le frecce per avanzare e ruotare. Pareti, fixture e aree vietate bloccano il movimento.",
    canvasLabel: "Walk-through del planogramma in prima persona con controllo collisioni",
  }),
  nl: Object.freeze({
    walk: "Rondgang",
    hint: "Klik in de scène om met de muis rond te kijken; beweeg met W/A/S/D en gebruik de pijltjestoetsen om te lopen en draaien. Muren, fixtures en verboden zones blokkeren beweging.",
    canvasLabel: "Eerstepersoons planogramrondgang met botsingscontrole",
  }),
  pl: Object.freeze({
    walk: "Spacer 3D",
    hint: "Kliknij scenę, aby rozglądać się myszą; poruszaj się klawiszami W/A/S/D, a strzałkami idź i obracaj widok. Ściany, wyposażenie i strefy zakazane blokują ruch.",
    canvasLabel: "Pierwszoosobowy spacer po planogramie z kontrolą kolizji",
  }),
  "pt-BR": Object.freeze({
    walk: "Caminhada 3D",
    hint: "Clique na cena para olhar com o mouse; mova-se com W/A/S/D e use as setas para andar e girar. Paredes, fixtures e áreas restritas bloqueiam o movimento.",
    canvasLabel: "Caminhada de planograma em primeira pessoa com controle de colisão",
  }),
});

export function translatePlanogramWalkthrough(locale, key) {
  const dictionary = PLANOGRAM_WALKTHROUGH_MESSAGES[locale] || PLANOGRAM_WALKTHROUGH_MESSAGES.en;
  return dictionary[key] || PLANOGRAM_WALKTHROUGH_MESSAGES.en[key] || key;
}
