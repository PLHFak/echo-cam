// Visiteur de la galerie (etape 4 du plan) :
// - reste sur SON rail lateral (jamais au centre, qui est la place de la
//   personne reelle), toujours oriente vers l'avant (+Z, sens de la marche) ;
// - machine a etats : marche -> arret contemplation devant une oeuvre ->
//   marche, durees et vitesses aleatoires ;
// - boucle : au bout de la galerie, retour silencieux au debut (galerie
//   infinie) ; pas de depassement, celui de derriere s'arrete.

using UnityEngine;

public class Visiteur : MonoBehaviour
{
    public float longueurBoucle = 36f;   // longueur totale (3 modules de 12 m)
    public float zDebut = -18f;
    [HideInInspector] public Visiteur devant;   // visiteur precedent sur le rail

    const float EspaceMini = 1.6f;       // distance minimale avec celui de devant

    float _vitesse;
    float _etatRestant;
    bool _marche = true;

    void Start()
    {
        _vitesse = Random.Range(0.6f, 1.1f);
        _etatRestant = Random.Range(2f, 8f);
    }

    void Update()
    {
        _etatRestant -= Time.deltaTime;  // Time.timeScale (ECHO) s'applique seul
        if (_etatRestant <= 0f)
        {
            _marche = !_marche;          // marche <-> contemplation
            _etatRestant = _marche ? Random.Range(4f, 10f) : Random.Range(2f, 6f);
            if (_marche) _vitesse = Random.Range(0.6f, 1.1f);
        }
        if (!_marche) return;

        // pas de depassement : si celui de devant est trop pres, on attend
        if (devant != null)
        {
            float ecart = devant.transform.position.z - transform.position.z;
            if (ecart < 0f) ecart += longueurBoucle;
            if (ecart < EspaceMini) return;
        }

        var p = transform.position;
        p.z += _vitesse * Time.deltaTime;
        if (p.z > zDebut + longueurBoucle) p.z -= longueurBoucle;  // boucle
        transform.position = p;
    }
}
