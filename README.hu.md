# Karmada hibrid cloud bursting labor

[English](README.md) | **Magyar**

Ez a labor egyetlen Windows + WSL2 + Docker Desktop gépen, négy különálló kind Kubernetes-clusterrel mutatja meg, hogyan osztja el a Karmada az alkalmazás replikáit a helyi clusterek és egy **szimulált** felhős cluster között. A FreeLens a clusterek vizsgálatára, a Grafana az események és metrikák követésére szolgál.

A részletes magyarázat, az architektúraábrák, a forgatókönyvek lépései és a Grafana-képernyőképek itt találhatók: **[A labor működése és architektúrája](docs/ARCHITECTURE.hu.md)**.

## Mit lehet megfigyelni?

| Cluster | Szerep |
| --- | --- |
| `karmada-mgmt` | Karmada vezérlősík és központi Prometheus, Loki, Grafana |
| `dc-primary`, `dc-secondary` | Elsődlegesen használt, helyszíni környezetet szimuláló tagclusterek |
| `cloud-azure` | Túlcsordulásra használt, helyben futó cloud-szimuláció; nem Azure-szolgáltatás |

A Karmada API-ban létrehozott `placement-demo` Deploymenthez egy `PropagationPolicy` rendel célclustereket. A policy a két on-prem clustert részesíti előnyben, és ha a becslés szerint ott nem fér el minden replika, a `cloud-azure` is kaphat belőlük. A Karmada a kívánt számot szétosztja; a tagclusterek Kubernetes-vezérlői hozzák létre és indítják el a Podokat. A **kívánt**, a **kiosztott** és a ténylegesen **Ready** replikaszám különböző állapot.

A labor három, egymástól elválasztott szcenáriót futtat:

- **Kézi burst:** a kívánt replikaszámot a parancs állítja: 4→8→10→16→22→8→4. A legutóbbi tesztben 10-ig az on-prem clusterek fogadták a replikákat; 22-nél a megoszlás 4+6+12 volt.
- **Automatikus burst:** a `FederatedHPA` a Podok CPU-kihasználtsága alapján változtatja a kívánt számot; a helyi terhelésgenerátorok leállítása után a rendszer visszaskáláz. Az 50%-os cél a Podok **CPU-requestjéhez viszonyított** kihasználtságra vonatkozik.
- **Cluster-failover:** a labor szünetelteti a `dc-primary` clustert, felismeri a kiesést, és megvizsgálja, hogy a `dc-secondary` clusteren el nem férő replikák Ready állapotba kerülnek-e a `cloud-azure` clusteren. A primary folytatása előtt 60 másodperces megfigyelési szakasz következik; a failover csak ideiglenesen, a tesztre kapcsol be, majd az eredeti beállítás áll vissza.

A 4/6/12 kapacitás egy erre a laborra számolt ütemezési cél: a foglaló Podok CPU-requesteket tartanak fenn. A három tag ugyanazon a fizikai gépen osztozik; ezek nem egymástól független fizikai erőforrások. A pontos eloszlás a tényleges kapacitástól és a scheduler állapotától függ.

## Indítás és mindennapi parancsok

A parancsokat a projekt gyökerében, WSL alatt futtasd:

```bash
make up             # létrehozza vagy összeegyezteti a labort, majd ellenőrzi
make verify         # aktuális állapot és adatfolyamok ellenőrzése
make demo-manual    # kézi 4→8→10→16→22→8→4
make demo-auto      # FederatedHPA terhelés, burst, visszaskálázás
make demo-failover  # kontrollált dc-primary pause, failover, visszaállítás
make reset-demo     # HPA és terhelés leállítása; vissza 4 Ready replikára
make down           # a nyilvántartott laborclusterek és helyi adataik törlése
```

A demókat egymás után futtasd; a parancsok a megfelelő induló állapotot állítják elő. A `make up` megtagadja a demó felülírását, ha aktív HPA, terhelésgenerátor vagy nem alapállapotú replikaszám található; ilyenkor előbb `make reset-demo` szükséges. A `make verify` ellenőrzési célú Kubernetes-eseményeket és Loki-markert hoz létre.

**A `make down` törli a labor clustereit és azok helyi Prometheus-, Loki- és Grafana-adatait.** A parancs azonosító alapján ellenőrzi a labor tulajdonát; a kind cluster törlése után a helyi PVC-k tartalma nem marad meg. Az újraépítés a FreeLens-kapcsolatokat is érinti.

### Előfeltételek

Windows, Ubuntu WSL2, Docker Desktop WSL-integráció, valamint `docker`, `kind` v0.33.0, `kubectl` v1.35.9, Helm v3.22.1, `karmadactl` v1.19.1, Python 3, Git, OpenSSL, curl és GNU make szükséges. A projekt WSL-es fájlrendszerben legyen, például `/home/<felhasználó>/karmada-lab` alatt. A tervezett WSL-memóriakeret kb. 20 GiB. A verziókat a [verziójegyzék](docs/VERSIONS.md), a rendelkezésre állást a `make preflight` ellenőrzi. A pinned eszközök telepítője: `install-karmada-wsl-tools.sh`.

## FreeLens és Grafana

A `make up` a négy kind kubeconfigot a privát `.runtime/freelens/` mappába, a Karmada API Windowsból használható konfigurációját a `.runtime/karmada/karmada-freelens.yaml` fájlba írja. Ezek hitelesítő adatokat tartalmaznak; ne kerüljenek Gitbe. A FreeLensben a `monitoring/grafana` Service-hez indított port-forwarddal érhető el a Grafana. Az adminjelszó helyben kérdezhető le:

```bash
kubectl --context kind-karmada-mgmt -n monitoring get secret grafana -o jsonpath='{.data.admin-password}' | base64 -d
```

A kind clusterek újraépítése után új tanúsítványok és kubeconfigok keletkeznek. A FreeLens **Add from kubeconfig** művelettel felvett bejegyzései saját másolatot használhatnak: ezeket újra kell importálni vagy frissíteni. A korábban szinkronizált bejegyzések eltávolítása a forrásfájlból is eltávolíthatja a kontextust; ilyen esetben a `make kind-up` újragenerálja a négy kind-kubeconfigot. A korábban megfigyelt FreeLens 503 pontos oka nem ismert; újonnan importált bejegyzésekkel mind az öt kapcsolat működött.

## Állapot és további dokumentáció

Az újraépített laboron a `make up`, `make verify`, a kézi és az automatikus demó sikeres volt. Az újraépítés első telepítési kísérlete a GitHub CRD-letöltésének időtúllépésén megállt; ellenőrzött gyorsítótárazott csomaggal az újrapróbálás sikerült. **Teljesen üres letöltési gyorsítótárból telepítés még nincs igazolva.** A Windows-gazdagép külön metrikái jelenleg nem prioritások.

- [Részletes architektúra és forgatókönyvek](docs/ARCHITECTURE.hu.md)
- [Demo runbook és diagnosztikai lekérdezések](scenarios/01-06-burst-runbook.md)
- [Cluster-failover forgatókönyv](scenarios/02-cluster-failover.hu.md) · [English](scenarios/02-cluster-failover.md) — kontrollált kiesés, megfigyelés és helyreállítás
- [Megfigyelési összetevők](observability/README.md)
- [Elvégzett ellenőrzések és korlátok](docs/VALIDATION_RESULTS.md)
- [Folyamatos munkanapló](docs/WORK_STATUS.md)
- [Elfogadási tesztek](docs/ACCEPTANCE_TESTS.md), [implementációs terv](docs/IMPLEMENTATION_PLAN.md), [architekturális döntések](docs/ARCHITECTURE_DECISIONS.md)
- [Karmada FederatedHPA dokumentáció](https://karmada.io/docs/userguide/autoscaling/federatedhpa/), [Karmada metrikaalapú autoskálázási útmutató](https://karmada.io/docs/tutorials/autoscaling-with-resource-metrics/), [Grafana Alloy](https://grafana.com/docs/alloy/latest/)
