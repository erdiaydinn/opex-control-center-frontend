export const ACADEMY_GRAPH_MESSAGES = Object.freeze({
  tr: { graphCanvas: "Senaryo grafiği", graphHint: "Düğümleri sürükleyin veya odaklandıktan sonra ok tuşlarıyla taşıyın. Bağlantılar sunucuya gönderilen gerçek senaryo kenarlarını gösterir.", selectedNode: "Seçili düğüm", removeNode: "Düğümü kaldır", removeEdge: "Bağlantıyı kaldır", cannotRemoveTerminal: "Senaryoda en az bir son düğüm kalmalıdır.", keyboardMove: "Ok tuşlarıyla taşı" },
  en: { graphCanvas: "Scenario graph", graphHint: "Drag nodes or move a focused node with the arrow keys. Connections represent the actual scenario edges submitted to the server.", selectedNode: "Selected node", removeNode: "Remove node", removeEdge: "Remove edge", cannotRemoveTerminal: "At least one terminal node must remain in the scenario.", keyboardMove: "Move with arrow keys" },
  de: { graphCanvas: "Szenariograf", graphHint: "Ziehen Sie Knoten oder verschieben Sie einen fokussierten Knoten mit den Pfeiltasten. Verbindungen zeigen die tatsächlich an den Server gesendeten Szenariokanten.", selectedNode: "Ausgewählter Knoten", removeNode: "Knoten entfernen", removeEdge: "Verbindung entfernen", cannotRemoveTerminal: "Im Szenario muss mindestens ein Endknoten verbleiben.", keyboardMove: "Mit Pfeiltasten verschieben" },
  ar: { graphCanvas: "مخطط السيناريو", graphHint: "اسحب العقد أو حرّك العقدة المركزة بمفاتيح الأسهم. تمثل الروابط حواف السيناريو الفعلية المرسلة إلى الخادم.", selectedNode: "العقدة المحددة", removeNode: "إزالة العقدة", removeEdge: "إزالة الرابط", cannotRemoveTerminal: "يجب أن تبقى عقدة نهائية واحدة على الأقل في السيناريو.", keyboardMove: "التحريك بمفاتيح الأسهم" },
  fr: { graphCanvas: "Graphe du scénario", graphHint: "Faites glisser les nœuds ou déplacez un nœud focalisé avec les flèches. Les connexions représentent les arêtes réellement envoyées au serveur.", selectedNode: "Nœud sélectionné", removeNode: "Supprimer le nœud", removeEdge: "Supprimer le lien", cannotRemoveTerminal: "Le scénario doit conserver au moins un nœud terminal.", keyboardMove: "Déplacer avec les flèches" },
  es: { graphCanvas: "Grafo del escenario", graphHint: "Arrastra los nodos o mueve el nodo enfocado con las flechas. Las conexiones representan las aristas reales enviadas al servidor.", selectedNode: "Nodo seleccionado", removeNode: "Eliminar nodo", removeEdge: "Eliminar enlace", cannotRemoveTerminal: "Debe quedar al menos un nodo terminal en el escenario.", keyboardMove: "Mover con las flechas" },
  it: { graphCanvas: "Grafo dello scenario", graphHint: "Trascina i nodi o sposta il nodo focalizzato con i tasti freccia. Le connessioni rappresentano gli archi reali inviati al server.", selectedNode: "Nodo selezionato", removeNode: "Rimuovi nodo", removeEdge: "Rimuovi collegamento", cannotRemoveTerminal: "Nello scenario deve rimanere almeno un nodo terminale.", keyboardMove: "Sposta con i tasti freccia" },
  nl: { graphCanvas: "Scenariograaf", graphHint: "Sleep knooppunten of verplaats een gefocust knooppunt met de pijltjestoetsen. Verbindingen zijn de werkelijke scenario-randen die naar de server gaan.", selectedNode: "Geselecteerd knooppunt", removeNode: "Knooppunt verwijderen", removeEdge: "Verbinding verwijderen", cannotRemoveTerminal: "Er moet minstens één eindknooppunt in het scenario blijven.", keyboardMove: "Verplaatsen met pijltjestoetsen" },
  pl: { graphCanvas: "Graf scenariusza", graphHint: "Przeciągaj węzły lub przesuwaj aktywny węzeł klawiszami strzałek. Połączenia odzwierciedlają rzeczywiste krawędzie scenariusza wysyłane do serwera.", selectedNode: "Wybrany węzeł", removeNode: "Usuń węzeł", removeEdge: "Usuń połączenie", cannotRemoveTerminal: "W scenariuszu musi pozostać co najmniej jeden węzeł końcowy.", keyboardMove: "Przesuwaj strzałkami" },
  "pt-BR": { graphCanvas: "Grafo do cenário", graphHint: "Arraste os nós ou mova o nó em foco com as setas. As conexões representam as arestas reais do cenário enviadas ao servidor.", selectedNode: "Nó selecionado", removeNode: "Remover nó", removeEdge: "Remover conexão", cannotRemoveTerminal: "Pelo menos um nó terminal deve permanecer no cenário.", keyboardMove: "Mover com as setas" },
});

export function translateAcademyGraph(locale, key) {
  return ACADEMY_GRAPH_MESSAGES[locale]?.[key] || ACADEMY_GRAPH_MESSAGES.en[key] || key;
}

export function academyGraphMessageCoverage(locales) {
  const keys = Object.keys(ACADEMY_GRAPH_MESSAGES.en).sort();
  return {
    missing: Object.fromEntries(locales.map((locale) => [locale, keys.filter((key) => typeof ACADEMY_GRAPH_MESSAGES[locale]?.[key] !== "string")])),
    extra: Object.fromEntries(locales.map((locale) => [locale, Object.keys(ACADEMY_GRAPH_MESSAGES[locale] || {}).filter((key) => !keys.includes(key)).sort()])),
  };
}
