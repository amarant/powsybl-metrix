Voici un plan d’investigation adapté au simulateur. **Je n’ai pas encore mesuré un profil CPU en production** : les points ci-dessous sont des hypothèses tirées du code, à départager par la mesure. Les durées des tests ASan ne doivent pas servir de référence de performance.

## 1. Fixer la cible et une référence reproductible

Mesurer séparément le **temps d’une variante**, le **débit sur plusieurs variantes** et le **pic mémoire**. Garder le même compilateur, les mêmes dépendances, les mêmes entrées et les mêmes options pour comparer deux versions.

Créer un build de profilage optimisé, distinct du build ASan. Dans ce projet, `Release` utilise `-O3` ; les options suivantes ajoutent les symboles et conservent les pointeurs de pile :

```bash
cmake -S metrix-simulator -B metrix-simulator/build-perf \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_FLAGS="-g -fno-omit-frame-pointer" \
  -Dsirius_solver_static_ROOT="$PWD/metrix-simulator/build/external/sirius_solver" \
  -DSUITESPARSE_HOME="$PWD/metrix-simulator/build/external/suitesparse"

cmake --build metrix-simulator/build-perf --parallel 2
```

Conserver le binaire et les mesures du commit de départ avant toute optimisation. Pour chaque scénario, faire un échauffement puis au moins cinq exécutions, et relever la médiane, la dispersion, le temps CPU et le pic RSS. `hyperfine` est présent sur cette machine et permet les répétitions et l’export des mesures ; `/usr/bin/time -v` donne notamment le pic RSS. [Documentation hyperfine](https://github.com/sharkdp/hyperfine), [manuel de time](https://man7.org/linux/man-pages/man1/time.1.html).

## 2. Choisir des scénarios qui isolent les coûts

| Scénario existant | Ce qu’il permet d’observer |
|---|---|
| `variantes_regroupees_complexe` | Réseau de 18 486 nœuds, 25 582 quadripôles et **11 variantes** : regroupement par topologie, réutilisation des matrices et débit. |
| `contraintes_sans_action_possible` | Grand réseau, une variante : construction du problème et recherche de contraintes. |
| `pompage_hr_necessaire` | 22 418 groupes : traitement des groupes et solveur. |
| `composante_non_connexe` | 44 728 nœuds, arrêt avant la résolution : lecture et analyse de connexité. |
| `LODF_PTDF_matrices` | Chemin de calcul et d’écriture des matrices de sortie. |

Lancer **le binaire directement** pour les chronométrages, depuis le répertoire du scénario avec `HADES_DIR=.` et `METRIX_ETC` définis comme dans [tests/CMakeLists.txt](/home/marrantarn/Projects/workspace/powsybl-metrix/metrix-simulator/tests/CMakeLists.txt:13). CTest reste le contrôle de non-régression ; son temps inclut le lancement et la comparaison des fichiers. Garder les sorties et les paramètres identiques entre mesures.

## 3. Attribuer le temps aux phases

Ajouter temporairement des compteurs et des chronomètres `std::chrono::steady_clock`, agrégés par phase et par variante, sans journaliser chaque contrainte. Le journal actuel emploie notamment `time()` à la seconde dans [metrix.cpp](/home/marrantarn/Projects/workspace/powsybl-metrix/metrix-simulator/src/metrix.cpp:111), ce qui ne suffit pas pour les sous-phases.

Relever au minimum :

- lecture du réseau, connexité et création des variantes ;
- construction et factorisation de la jacobienne, puis nombre de refactorisations ;
- nombre de variantes par topologie et nombre de micro-itérations par variante ;
- temps passé dans Sirius Solver, dans `detectionContraintes`, dans `ajoutContraintes` et dans les rapports ;
- tailles des matrices, nombre de variables et de contraintes, nombre d’allocations et pic mémoire.

Le parcours principal est visible dans [resolutionProbleme](/home/marrantarn/Projects/workspace/powsybl-metrix/metrix-simulator/src/calculmacrofonctions.cpp:201) et sa boucle de micro-itérations dans [resolutionUnProblemeDodu](/home/marrantarn/Projects/workspace/powsybl-metrix/metrix-simulator/src/calculmacrofonctions.cpp:565). Ce découpage dira si le gain potentiel se situe dans notre code ou dans Sirius Solver/SuiteSparse.

## 4. Profiler, puis classer les hypothèses

Sur cette machine, `perf stat` est actuellement refusé : `perf_event_paranoid=4`. Si l’accès au profilage est accordé par l’administrateur, collecter un profil avec `perf record --call-graph dwarf`, puis examiner `perf report`. Sinon, les chronomètres par phase restent utilisables. Le noyau documente cette restriction et la capacité `CAP_PERFMON`. [Manuel perf](https://man7.org/linux/man-pages/man1/perf-record.1.html), [documentation du noyau](https://docs.kernel.org/admin-guide/perf-security.html).

Examiner les pistes suivantes **dans l’ordre indiqué par le profil**, pas toutes à la fois :

| Piste | Observation à rechercher | Expérience éventuelle |
|---|---|---|
| Solveur et matrices | Part du temps dans `PneSolveur`, `LU_Factorisation`, `LU_LuSolv` et les refactorisations | Vérifier les matrices reconstruites inutilement et les possibilités de réutilisation. Le démarrage à chaud du simplexe exige de valider la base et les résultats numériques. |
| Détection des contraintes | Temps par incident et élément surveillé dans [detectionContraintes](/home/marrantarn/Projects/workspace/powsybl-metrix/metrix-simulator/src/calculecrirecontraintesdodu.cpp:2153) | Éviter des calculs répétés seulement si les compteurs et le profil les montrent coûteux. |
| Variantes | Coût du regroupement par topologie dans [updateVariants](/home/marrantarn/Projects/workspace/powsybl-metrix/metrix-simulator/src/reseau.cpp:2808) et des comparaisons d’ensembles dans [CompareSet](/home/marrantarn/Projects/workspace/powsybl-metrix/metrix-simulator/src/variante.h:106) | Tester une représentation de clé plus compacte si les comparaisons apparaissent dans le profil. |
| Allocations | Nombre de petites allocations et pic mémoire lors de la lecture et de la création des contraintes | Utiliser un profileur d’allocations tel que [heaptrack](https://github.com/KDE/heaptrack), absent actuellement, avant de modifier les conteneurs. |
| Rapports | Temps dans [metrix2Assess](/home/marrantarn/Projects/workspace/powsybl-metrix/metrix-simulator/src/metrix2assess.cpp:193) et volume écrit | Mesurer le calcul et l’écriture séparément avant de toucher au format des sorties. |

Si le profil pointe vers Sirius Solver ou SuiteSparse, reconstruire aussi la dépendance concernée avec symboles de débogage pour attribuer le coût à ses fonctions.

## 5. Expérimenter avec des critères d’acceptation

Pour chaque optimisation : une hypothèse, un changement isolé, les mêmes scénarios répétés, puis comparaison des médianes **et** du pic mémoire. Conserver uniquement un gain supérieur à la variabilité des mesures et sans régression importante sur les autres scénarios.

Exécuter ensuite les **113 tests CTest** et la passe ASan/LSan documentée dans [ASAN_LSAN.md](/home/marrantarn/Projects/workspace/powsybl-metrix/metrix-simulator/ASAN_LSAN.md). Ajouter un contrôle numérique spécifique au benchmark `variantes_regroupees_complexe` : son test actuel vérifie l’exécution, mais ne compare pas les sorties en raison de solutions équivalentes. Il faut au moins contrôler les statuts, l’objectif et les contraintes avec des tolérances métier convenues.

**Premier livrable utile :** un tableau « scénario → temps total, pic RSS, temps par phase, appels solveur, micro-itérations ». Il permettra de choisir le premier changement avec une preuve du coût visé.