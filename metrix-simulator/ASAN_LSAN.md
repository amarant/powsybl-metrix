# Détecter les erreurs mémoire avec ASan et LSan

Ce guide s'exécute depuis la racine du dépôt, sous Linux, avec GCC. ASan (AddressSanitizer) détecte notamment les accès hors limites et les utilisations après libération. LSan (LeakSanitizer) recherche les allocations encore perdues à la fin du processus. Sur Linux, la compilation avec ASan permet d'activer LSan à l'exécution.

## Prérequis

Sur Ubuntu/Debian, installer un compilateur C++ et CMake suffit pour disposer de l'instrumentation ASan/LSan de GCC :

~~~bash
sudo apt update
sudo apt install build-essential cmake git
~~~

Le simulateur requiert aussi Boost (system, program_options, log, filesystem), Sirius Solver et SuiteSparse. Si Boost manque :

~~~bash
sudo apt install libboost-system-dev libboost-program-options-dev libboost-log-dev libboost-filesystem-dev
~~~

Si les deux bibliothèques externes ne sont pas encore construites, utiliser la configuration fournie par le projet (elle télécharge les sources) :

~~~bash
cmake -S metrix-simulator/external -B metrix-simulator/build/external
cmake --build metrix-simulator/build/external --parallel 2
~~~

Les installations produites se trouvent normalement dans metrix-simulator/build/external/sirius_solver et metrix-simulator/build/external/suitesparse.

## Compiler le binaire instrumenté

Créer un répertoire de compilation distinct de la version normale. Les options de compilation ajoutent les contrôles ASan et les informations nécessaires aux traces ; l'option de liaison charge son runtime dans le binaire final.

~~~bash
cmake -S metrix-simulator -B metrix-simulator/build-asan \
  -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_CXX_FLAGS="-fsanitize=address -fno-omit-frame-pointer" \
  -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address" \
  -Dsirius_solver_static_ROOT="$PWD/metrix-simulator/build/external/sirius_solver" \
  -DSUITESPARSE_HOME="$PWD/metrix-simulator/build/external/suitesparse"

cmake --build metrix-simulator/build-asan --parallel 2
~~~

Le binaire obtenu est metrix-simulator/build-asan/metrix-simulator. Il faut recompiler après chaque modification du code. Les dépendances déjà compilées sans instrumentation ne seront pas vérifiées à l'intérieur de leurs propres fonctions.

Si CMake ne trouve pas sirius_solver_staticConfig.cmake, vérifier que Sirius Solver a bien été construit et que le chemin donné à sirius_solver_static_ROOT contient son installation. Pour SuiteSparse, vérifier SUITESPARSE_HOME.

## Exécuter les tests avec détection des fuites

L'option detect_leaks=1 active explicitement LSan avec ce binaire ASan. CTest transmet la variable d'environnement au simulateur qu'il lance.

~~~bash
ASAN_OPTIONS=detect_leaks=1 \
  ctest --test-dir metrix-simulator/build-asan \
  --output-on-failure --parallel 2
~~~

Pour reproduire un seul scénario et voir son rapport en cas d'échec :

~~~bash
ASAN_OPTIONS=detect_leaks=1 \
  ctest --test-dir metrix-simulator/build-asan \
  --output-on-failure -R '^encodage_utf8$'
~~~

Réduire ou retirer --parallel si plusieurs gros scénarios utilisent trop de mémoire. Les tests utilisent les fichiers d'entrée de metrix-simulator/tests et comparent leurs sorties aux références.

## Exécuter directement le simulateur

Lancer le binaire depuis le répertoire du scénario pour qu'il trouve ses fichiers d'entrée. Cet exemple utilise le même scénario que le test CTest ci-dessus :

~~~bash
repo_root="$PWD"
(
  cd "$repo_root/metrix-simulator/tests/divers/encodage_utf8"
  HADES_DIR=. \
  METRIX_ETC="$repo_root/metrix-simulator/etc" \
  ASAN_OPTIONS=detect_leaks=1 \
    "$repo_root/metrix-simulator/build-asan/metrix-simulator" \
    metrixOut.txt VariantSet.csv out 0 2
)
~~~

ASan et LSan écrivent leurs diagnostics sur la sortie d'erreur et font échouer le processus lorsqu'ils détectent une erreur. Une trace ASan indique l'accès fautif et, souvent, l'allocation concernée. Un rapport LSan distingue les fuites directes des fuites indirectes et indique les piles d'allocation. Commencer par la première erreur, la corriger, recompiler, puis relancer : un arrêt anticipé peut masquer d'autres problèmes.

Pour conserver le rapport d'un test :

~~~bash
ASAN_OPTIONS=detect_leaks=1 \
  ctest --test-dir metrix-simulator/build-asan \
  --output-on-failure -R '^encodage_utf8$' \
  > /tmp/metrix-asan-test.log 2>&1
~~~

Un test qui passe sans rapport signifie qu'aucune erreur n'a été détectée sur les chemins exécutés par ce test ; cela ne prouve pas que tous les chemins du programme sont exempts de fuites.

## LSan seul, si nécessaire

Pour rechercher uniquement les fuites avec GCC, créer un autre répertoire de compilation et lier le runtime LSan. Utiliser un répertoire distinct pour éviter de réemployer les options ASan de l'autre build. La configuration ASan ci-dessus couvre déjà les fuites sur Linux.

~~~bash
cmake -S metrix-simulator -B metrix-simulator/build-lsan \
  -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_CXX_FLAGS="-fsanitize=leak -fno-omit-frame-pointer" \
  -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=leak" \
  -Dsirius_solver_static_ROOT="$PWD/metrix-simulator/build/external/sirius_solver" \
  -DSUITESPARSE_HOME="$PWD/metrix-simulator/build/external/suitesparse"

cmake --build metrix-simulator/build-lsan --parallel 2
ctest --test-dir metrix-simulator/build-lsan --output-on-failure --parallel 2
~~~

## Documentation des outils

- [GCC : options d'instrumentation](https://gcc.gnu.org/onlinedocs/gcc/Instrumentation-Options.html)
- [LLVM : AddressSanitizer](https://clang.llvm.org/docs/AddressSanitizer.html)
- [LLVM : LeakSanitizer et LSAN_OPTIONS](https://clang.llvm.org/docs/LeakSanitizer.html)

