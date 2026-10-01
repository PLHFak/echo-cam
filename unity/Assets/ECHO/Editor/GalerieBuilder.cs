// Construit toute la scene "galerie" d'un clic : menu ECHO -> Construire la
// galerie. Couloir de 3 modules de 12 m (boucle des visiteurs = 36 m),
// oeuvres encadrees sur les murs, statues sur socles, visiteurs sur les deux
// rails lateraux (le centre reste vide : c'est la place de la personne),
// camera fixe au centre + emetteur Spout (KlakSpout, ajoute si present),
// horloge asservie a ECHO (EchoLink).

using System;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class GalerieBuilder
{
    const float Module = 12f;        // longueur d'un module (m)
    const int NbModules = 3;
    const float Largeur = 6f;        // largeur du couloir
    const float Hauteur = 3.6f;
    const float ZDebut = -18f;       // z du debut de la boucle

    [MenuItem("ECHO/Construire la galerie")]
    public static void Construire()
    {
        if (Application.isBatchMode)             // installeur : scene neuve
            EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects,
                                        NewSceneMode.Single);
        var ancien = GameObject.Find("GALERIE");
        if (ancien != null) UnityEngine.Object.DestroyImmediate(ancien);
        var racine = new GameObject("GALERIE");
        UnityEngine.Random.InitState(7);

        var murMat    = Mat(new Color(0.88f, 0.86f, 0.82f));
        var solMat    = Mat(new Color(0.35f, 0.32f, 0.30f));
        var cadreMat  = Mat(new Color(0.12f, 0.12f, 0.12f));
        var socleMat  = Mat(new Color(0.75f, 0.74f, 0.72f));
        var statueMat = Mat(new Color(0.92f, 0.91f, 0.88f));

        for (int m = 0; m < NbModules; m++)
        {
            float z0 = ZDebut + m * Module + Module / 2f;
            var mod = new GameObject("Module_" + m);
            mod.transform.parent = racine.transform;

            Bloc(mod, "Sol", new Vector3(0, -0.05f, z0),
                 new Vector3(Largeur, 0.1f, Module), solMat);
            Bloc(mod, "MurG", new Vector3(-Largeur / 2f, Hauteur / 2f, z0),
                 new Vector3(0.1f, Hauteur, Module), murMat);
            Bloc(mod, "MurD", new Vector3(Largeur / 2f, Hauteur / 2f, z0),
                 new Vector3(0.1f, Hauteur, Module), murMat);
            Bloc(mod, "Plafond", new Vector3(0, Hauteur, z0),
                 new Vector3(Largeur, 0.1f, Module), murMat);

            for (int cote = -1; cote <= 1; cote += 2)        // oeuvres aux murs
                for (int i = 0; i < 3; i++)
                {
                    float z = z0 - Module / 2f + (i + 0.5f) * Module / 3f;
                    float x = cote * (Largeur / 2f - 0.08f);
                    Bloc(mod, "Cadre", new Vector3(x, 1.7f, z),
                         new Vector3(0.06f, 1.3f, 1.0f), cadreMat);
                    Bloc(mod, "Oeuvre", new Vector3(x - cote * 0.02f, 1.7f, z),
                         new Vector3(0.06f, 1.1f, 0.8f),
                         Mat(UnityEngine.Random.ColorHSV(0f, 1f, 0.4f, 0.9f, 0.4f, 0.9f)));
                }

            for (int cote = -1; cote <= 1; cote += 2)        // statues sur socles
            {
                float z = z0 + (cote > 0 ? -Module / 4f : Module / 4f);
                float x = cote * (Largeur / 2f - 0.75f);
                Bloc(mod, "Socle", new Vector3(x, 0.5f, z),
                     new Vector3(0.6f, 1.0f, 0.6f), socleMat);
                var forme = (m + (cote > 0 ? 1 : 0)) % 3;
                var prim = forme == 0 ? PrimitiveType.Sphere :
                           forme == 1 ? PrimitiveType.Capsule : PrimitiveType.Cylinder;
                var st = GameObject.CreatePrimitive(prim);
                st.name = "Statue";
                st.transform.parent = mod.transform;
                st.transform.position = new Vector3(x, 1.45f, z);
                st.transform.localScale = new Vector3(0.45f, 0.45f, 0.45f);
                st.GetComponent<Renderer>().sharedMaterial = statueMat;
            }

            var lampe = new GameObject("Lampe").AddComponent<Light>();
            lampe.transform.parent = mod.transform;
            lampe.transform.position = new Vector3(0, Hauteur - 0.2f, z0);
            lampe.type = LightType.Point;
            lampe.range = 10f;
            lampe.intensity = 1.4f;
        }

        // visiteurs : deux rails lateraux, tous vers +Z, jamais au centre
        float boucle = Module * NbModules;
        foreach (float xRail in new[] { -1.5f, 1.5f })
        {
            Visiteur precedent = null, premier = null;
            int n = 4;
            for (int i = 0; i < n; i++)
            {
                var v = GameObject.CreatePrimitive(PrimitiveType.Capsule);
                v.name = "Visiteur";
                v.transform.parent = racine.transform;
                float z = ZDebut + (i + UnityEngine.Random.Range(0.2f, 0.8f)) * boucle / n;
                v.transform.position = new Vector3(xRail, 0.9f, z);
                v.transform.localScale = new Vector3(0.45f, 0.9f, 0.45f);
                v.GetComponent<Renderer>().sharedMaterial =
                    Mat(UnityEngine.Random.ColorHSV(0f, 1f, 0.15f, 0.4f, 0.25f, 0.55f));
                var vis = v.AddComponent<Visiteur>();
                vis.longueurBoucle = boucle;
                vis.zDebut = ZDebut;
                if (precedent != null) precedent.devant = vis;
                else premier = vis;
                precedent = vis;
            }
            if (precedent != null) precedent.devant = premier;   // file circulaire
        }

        // camera fixe au centre, regard vers l'avant + emetteur Spout
        var cam = Camera.main;
        if (cam == null)
        {
            var go = new GameObject("Main Camera");
            go.tag = "MainCamera";
            cam = go.AddComponent<Camera>();
        }
        cam.transform.position = new Vector3(0, 1.6f, ZDebut + 1f);
        cam.transform.rotation = Quaternion.identity;
        cam.backgroundColor = new Color(0.05f, 0.05f, 0.06f);
        var spout = Type.GetType("Klak.Spout.SpoutSender, Klak.Spout.Runtime");
        if (spout != null)
        {
            if (cam.GetComponent(spout) == null) cam.gameObject.AddComponent(spout);
            Debug.Log("[ECHO] Emetteur Spout ajoute a la camera.");
        }
        else
            Debug.LogWarning("[ECHO] KlakSpout absent : installer le paquet "
                             + "jp.keijiro.klak.spout (voir README-UNITY.md).");

        // horloge asservie a ECHO
        var echo = new GameObject("ECHO");
        echo.transform.parent = racine.transform;
        echo.AddComponent<EchoLink>();

        Selection.activeGameObject = racine;
        EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene(),
                                     "Assets/ECHO/Galerie.unity");
        Debug.Log("[ECHO] Galerie construite et sauvee : Play pour la faire vivre.");
    }

    static Material Mat(Color c)
    {
        var sh = Shader.Find("Standard");
        if (sh == null) sh = Shader.Find("Universal Render Pipeline/Lit");
        var m = new Material(sh);
        m.color = c;
        if (m.HasProperty("_BaseColor")) m.SetColor("_BaseColor", c);
        return m;
    }

    static void Bloc(GameObject parent, string nom, Vector3 pos, Vector3 taille,
                     Material mat)
    {
        var b = GameObject.CreatePrimitive(PrimitiveType.Cube);
        b.name = nom;
        b.transform.parent = parent.transform;
        b.transform.position = pos;
        b.transform.localScale = taille;
        b.GetComponent<Renderer>().sharedMaterial = mat;
    }
}
