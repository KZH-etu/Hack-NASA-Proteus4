# Étude des données PSI : une table unique est-elle possible ?

Étude faite le samedi 14 novembre 2026 à partir des fichiers « Experimental table » de PSI (téléchargés dans `data/raw/psi/`, non versionnés) et du rapport NASA/TM-20210011385 (BASS-II).

## 1. Ce qui existe réellement

| Expérience | PSI / DOI | Lignes | Type | O2 | Pression | Débit | Issue (outcome) | Mesure quantitative |
|---|---|---|---|---|---|---|---|---|
| BASS | PSI-26 · 10.60555/58h4-dy80 | 122 | solide | dans l'Excel « As Run » | idem (atm) | « Air display », souvent une rampe (`10, 5, 3`) | texte libre (« Test Observations ») | — |
| BASS-II | PSI-25 · 10.60555/4qc4-de67 | 129 | solide | ✅ initial + final (13,6–22,2 %) | ❌ | « Air display », rampe ou potentiomètre | ❌ dans le CSV, texte libre dans l'annexe A du rapport | ❌ (voir §4) |
| FLEX | PSI-69 · 10.60555/mbq8-0451 | 274 | gouttelette | ✅ 12–34 % | ✅ (mmHg) | pas d'écoulement imposé | ✅ Extinction 186 / Disruption 61 / Completion 27 | diamètre initial, diamètre d'extinction, burning rate, burn time |
| Saffire I | PSI-98 · 10.60555/0t15-1z43 | 2 essais | solide (grand) | ~21,5 % | — | 20 cm/s | burn time | — |
| Saffire II | PSI-99 · 10.60555/2chp-m469 | 9 essais | solide | ~22 % | — | 20 cm/s | burn length | spread rate µg **et** 1g (quelques valeurs) |
| Saffire III | PSI-100 · 10.60555/040q-4h36 | 2 essais | solide (grand) | — | — | 30 cm/s | — | — |
| ACME Flame Design | PSI-10 · 10.60555/w4zy-bt45 | 207 + 120 | gaz (normale / inverse) | ✅ fraction molaire | ✅ (atm) | débits massiques (mg/s) | ❌ | Tad, Zst |
| ACME s-Flame | PSI-23 · 10.60555/k57n-p030 | 18 | gaz | approx. (« ~21 % ») | ~1 atm | — | nb de flammes allumées **par jour** | — |
| ACME CFI-G | PSI-159 · 10.60555/cyt1-kh64 | 179 + 154 | gaz (flammes froides) | ✅ | ✅ (bar, 0,5–3,3) | débits massiques | ✅ allumage oui/non, auto-extinction / coupure | burn time, température brûleur |
| SAME / SAME-R | PSI-102 · 10.60555/gd4k-8h62 / PSI-101 · 10.60555/2np7-jv14 | 8 + 109 | fumées (détecteurs) | — | — | ✅ | — | rapport de résistance, temps de vieillissement |

Toutes ces données sont en **microgravité (ISS)**. Seul Saffire-II donne aussi des valeurs en 1g, sur les mêmes échantillons.

## 2. Une table unique : oui pour le catalogue, non pour le modèle

**Pour l'onglet Explorer et la Carte des trous : oui.** Avec le schéma `src/common/schema.py`, on peut empiler BASS, BASS-II, FLEX, Saffire, ACME et SAME dans une seule table d'environ 1 300 lignes. Beaucoup de cases resteront vides, ce qui est normal. Cette table sert à montrer quelles conditions ont déjà été testées (matériau × O2 × pression × débit).

**Pour entraîner un seul modèle : non.** Les issues ne veulent pas dire la même chose d'une famille à l'autre :
- l'« extinction » d'une gouttelette sans écoulement (FLEX) ;
- l'« extinction » d'un solide quand on baisse le débit (BASS-II) ;
- l'« absence d'allumage » d'une flamme gazeuse (CFI-G).

Ce sont trois phénomènes physiques différents, avec des variables différentes. FLEX n'a pas de débit, BASS-II n'a pas de pression, ACME a des débits massiques et non des vitesses. Les mélanger donnerait un modèle sans signification.

## 3. Ce qu'on propose (deux niveaux)

**Niveau 1 : table catalogue unifiée** (`data/processed/unified.parquet`)
- Une ligne par essai, au format du schéma actuel, avec les vides assumés.
- Elle sert à l'Explorer, à la Carte des trous et au RAG (contexte).

**Niveau 2 : une table de modélisation par famille**

| Table | Lignes | Cible | Variables | Effort |
|---|---|---|---|---|
| `flex_model` (gouttelettes) | 274 | extinction / disruption / completion | carburant, O2, pression, diluant (CO2, He), diamètre initial | **faible** : tout est déjà structuré |
| `cfig_model` (gaz) | 333 | allumage oui/non, auto-extinction | carburant, O2, pression, débits | faible à moyen (casse à harmoniser : `Yes` / `yes`) |
| `bass2_model` (solides) | ~129 | extinction à bas débit oui/non, débit limite | matériau, épaisseur, O2, débit | **moyen** : il faut annoter l'issue à la main à partir de l'annexe A (texte), et convertir le potentiomètre en cm/s avec `PSI-25_Reference Data_Fan calibration data.xlsx` |

**Recommandation pour le ML :** commencer par **FLEX**, qui est prêt à l'emploi et le plus riche. Ajouter CFI-G si le temps le permet. BASS-II ne vient qu'après annotation. Pour la validation, découper par campagne (préfixe de l'identifiant FLEX ou date d'essai), pas aléatoirement.

**Le scénario de démo tombe dans un trou de données, et c'est notre argument :**
- L'atmosphère d'exploration NASA est d'environ 56,5 kPa (0,57 atm) avec 34 % d'O2 (à vérifier dans NASA/TP-2010-216134).
- FLEX n'est jamais descendu sous **70,2 kPa (0,69 atm)**.
- Seuls **24 essais** FLEX ont 30 % d'O2 ou plus, tous entre 71 et 103 kPa.

Le scénario « habitat lunaire enrichi en O2 » est donc **hors des données mesurées**. Le modèle doit le dire (« extrapolation ») et l'onglet « Prochaine expérience » doit proposer les essais qui combleraient ce trou.

## 4. Corrections à apporter au plan initial

- **Les vitesses de propagation BASS-II ne sont pas dans l'annexe A** du rapport NASA/TM-20210011385 (pp. 103–113 du document, pages 111–121 du PDF). L'annexe donne les matrices d'essais : O2, sens de l'écoulement, réglages ventilateur et observations en texte libre (« extinguished at pot 0.35 », etc.). Les vitesses n'apparaissent que dans le corps du rapport (figures et quelques valeurs dans le texte, ex. 2,2 mm/s). On n'aura donc pas de colonne `spread_rate_mm_s` remplie pour BASS-II, sauf saisie manuelle de quelques valeurs avec leur page.
- **SAME / SAME-R :** PSI-101 correspond à SAME-R (DOI 10.60555/2np7-jv14) et PSI-102 à SAME (DOI 10.60555/gd4k-8h62). Ce sont des données de fumée, pas de comportement de flamme. On peut les mettre hors périmètre pour le modèle.
- **CFI-G :** son DOI est 10.60555/cyt1-kh64.

## 5. Pièges de nettoyage repérés

Le détail, cas par cas (vrai manquant, sans objet, valeur documentée, faux zéro, incohérence), est dans [`regles_valeurs_manquantes.md`](regles_valeurs_manquantes.md).

- `PSI-69_Experimental table_FLEX.csv` est encodé en **cp1252** (pas UTF-8) : `pd.read_csv(..., encoding="cp1252")`.
- FLEX, essai `C11M201` : pression = 0 mmHg, ce qui est une valeur manquante. Elle doit devenir vide, pas 0.
- FLEX, colonne « Burning rate; mm » : l'unité est ambiguë (probablement mm²/s, la constante de combustion K). À vérifier dans NASA/TP-2015-216046 avant affichage.
- BASS / BASS-II : « Fan display » et « Air display » contiennent souvent plusieurs valeurs (rampes : `5, 4, 3, 2, 1`, `10, max`). Il faut garder la chaîne brute dans `notes` et n'extraire qu'une valeur quand elle est sans ambiguïté.
- CFI-G : la table « Inverse Flames » a 1 015 lignes dont seulement 154 remplies (supprimer les lignes vides). La casse est incohérente (`Yes` / `yes`, `Inverse` / `inverse`).
- ACME Flame Design : certaines valeurs sont la chaîne `RAMPED` au lieu d'un nombre.
- Saffire : les unités sont dans les cellules (`20 cm/s`, `0.27 mm`), avec des fourchettes (`22.1 to 22.0`) et des renvois (`Note 4`).
- ACME s-Flame : une ligne correspond à **un jour d'essais**, pas à un essai.

## 6. Évolutions possibles du schéma (à discuter, petite PR)

Colonnes qui seraient utiles pour ne rien perdre :
- `flow_direction` (opposed / concurrent) : BASS-II, Saffire ;
- `diluent` (N2 / CO2 / He) : FLEX, ACME ;
- `flame_type` (normal / inverse) : ACME ;
- `burn_time_s`, `extinction_diameter_mm` : FLEX, CFI-G, Saffire ;
- `outcome_raw` (texte d'origine) et `outcome_method` (`table` si la valeur vient directement de la source, `annotated` si l'équipe l'a déduite d'un texte, avec la page dans `source_page`). Cela respecte la règle « jamais de données inventées ».

## 7. Accès aux fichiers PSI (pour le script de téléchargement)

Le site PSI est une application web, mais son API est publique et ne demande pas de compte :
- métadonnées et liste des fichiers d'une investigation : `GET https://psi.nasa.gov/geode-py/ws/repo/investigations/PSI-25` (le champ `experimentalTable` liste les CSV) ;
- lien de téléchargement : `GET https://psi.nasa.gov/geode-py/ws/studies/PSI-25/download?file=<file_name>&redirect=false`, qui renvoie une URL S3 temporaire à télécharger ensuite.

## 8. Comparaison avec un autre projet sur le même challenge (Krypton-N/NASA-SPACE-APPS)

Dépôt public d'une autre équipe, préparé en amont (commits d'octobre à début novembre 2026), en espagnol, **sans licence**. On s'en sert comme source d'idées, sans reprendre de code ni de fichiers. Les données PSI étant en CC0, on les retélécharge nous-mêmes.

### Ce qu'ils ont de solide
- **Données très complètes :** 24 investigations PSI (dont **CFI PSI-39** et **SPICE PSI-107**, qu'on n'avait pas listées), 277 documents NTRS et le NASA Task Book.
- **Nettoyage par familles physiques** (gouttelettes / gaz / solides / aérosols / journaux par jour). C'est la même conclusion que notre §2 : pas de table de modélisation unique.
- **Traçabilité :** chaque valeur interprétée porte un drapeau qualité (`qc_flags`), avec un rapport de qualité.
- **Un dashboard soigné** avec rendu 3D de la flamme (qualitatif, ils le disent eux-mêmes).

### Leurs limites, donc nos points d'amélioration

| Domaine | Leur version | Ce qu'on peut faire mieux |
|---|---|---|
| **Modèle** | k plus proches voisins (k = 7) sur FLEX uniquement, gouttelettes seulement | Gaussian Process ou ensemble sur FLEX **et** CFI-G (et BASS-II si on l'annote), un modèle par famille |
| **Incertitude** | écart-type des 7 voisins, non calibré | variance prédictive du GP et intervalles vérifiés (couverture réelle des intervalles à 90 %) |
| **Validation** | leave-one-out sur 257 essais (R² = 0,68, 83 % d'accuracy). Avec des essais répétés et 18 identifiants dupliqués, c'est probablement optimiste | validation **par campagne ou par jour d'essai**, chiffres annoncés tels quels, même plus bas |
| **Hors domaine** | message « Extrapolando » quand on sort de la plage mesurée | on va plus loin : **on recommande l'expérience qui comble le trou**. C'est notre fonctionnalité centrale, absente chez eux |
| **Découpage RAG** | **un seul chunk par document** (titre + 1 500 premiers caractères), donc la recherche ne voit que l'introduction | découpage complet en chunks **avec numéro de page** |
| **Recherche RAG** | vectorielle seule (Titan + IVF maison), top-3 | hybride BM25 + embeddings avec fusion RRF, puis reranking si on a le temps |
| **« Je ne sais pas »** | aucun seuil : le LLM répond toujours, même si les documents trouvés sont hors sujet | seuil de pertinence, sinon réponse « je ne sais pas » |
| **Citations** | au niveau du document (titre), extrait de 500 caractères | titre + id NTRS + **page**, lien cliquable |
| **Évaluation RAG** | aucune | 20 questions de référence, comparaison vectoriel vs hybride, latence |
| **Démo en ligne** | l'assistant dépend d'AWS Bedrock et d'un serveur local (`127.0.0.1:5005`), donc il ne marche pas dans une démo publique | Streamlit Cloud avec la clé dans les secrets : tout fonctionne en ligne, y compris l'assistant |
| **1g vs microgravité** | évoqué comme hypothèse (Saffire-II) | couche de comparaison explicite 1g / µg dans l'Explorer |

### Ce qu'on retient pour notre plan
1. **Ajouter CFI (PSI-39, ~87 gouttelettes) et SPICE (PSI-107, ~469 flammes gaz)** à la liste de téléchargement. FLEX-2 (PSI-68) n'a qu'une matrice de conception, pas d'essais réalisés.
2. **Reprendre l'idée des drapeaux qualité** sous une forme simple (`outcome_method` et `notes`, cf. §6).
3. **Mettre le trou de couverture au centre du pitch :** atmosphère d'exploration (0,57 atm, 34 % O2) contre FLEX (≥ 0,69 atm). Eux le montrent ; nous, on dit quoi tester ensuite et pourquoi.
