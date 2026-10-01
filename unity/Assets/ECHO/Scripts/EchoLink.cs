// EchoLink : horloge de la galerie asservie a ECHO (etape 5 du plan).
// Se connecte au pont WebSocket d'ECHO (ws://localhost:8765), lit la vitesse
// de lecture et regle Time.timeScale : la galerie ralentit, se fige et
// repart avec la personne. Reconnexion automatique si ECHO n'est pas lance.

using System;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

public class EchoLink : MonoBehaviour
{
    [Serializable]
    class EtatEcho { public float v = 1f; public string etat = ""; }

    [Tooltip("Adresse du pont ECHO")]
    public string url = "ws://localhost:8765";
    [Tooltip("Lissage de l'horloge (0 = fige, 1 = instantane)")]
    [Range(0.01f, 1f)] public float lissage = 0.2f;
    [Tooltip("Echelle de temps maximale")]
    public float timeScaleMax = 2f;

    public static float VitesseEcho { get; private set; } = 1f;
    public static bool Connecte { get; private set; }

    float _cible = 1f;

    void Start() { _ = Boucle(); }

    void Update()
    {
        float ts = Mathf.Lerp(Time.timeScale, _cible, lissage);
        Time.timeScale = Mathf.Clamp(ts, 0f, timeScaleMax);
        VitesseEcho = Time.timeScale;
    }

    async Task Boucle()
    {
        var buf = new byte[65536];
        while (this != null)
        {
            using (var ws = new ClientWebSocket())
            {
                try
                {
                    await ws.ConnectAsync(new Uri(url), CancellationToken.None);
                    Connecte = true;
                    Debug.Log("[ECHO] connecte a " + url);
                    while (ws.State == WebSocketState.Open)
                    {
                        var res = await ws.ReceiveAsync(
                            new ArraySegment<byte>(buf), CancellationToken.None);
                        if (res.MessageType == WebSocketMessageType.Close) break;
                        var json = Encoding.UTF8.GetString(buf, 0, res.Count);
                        var etat = JsonUtility.FromJson<EtatEcho>(json);
                        if (etat != null) _cible = Mathf.Max(0f, etat.v);
                    }
                }
                catch (Exception) { /* ECHO pas lance : on reessaie */ }
            }
            Connecte = false;
            _cible = 1f;                      // sans ECHO : galerie au reel
            await Task.Delay(1000);
        }
    }
}
