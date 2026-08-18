import { Sheet } from './ui.jsx';
import { CAVEATS } from './DetailCard.jsx';

/**
 * Where the explanatory prose went.
 *
 * The dashboard used to carry all of this permanently: a scene description banner, two
 * caveat paragraphs quoting measured error figures, and two footnotes under the layer
 * list. None of it is deleted, because several of those numbers are the point of the
 * research. It is one click away instead of always on screen.
 */
export default function AboutSheet({ open, onClose, scene, sources }) {
  return (
    <Sheet title="About this data" open={open} onClose={onClose}>
      {scene?.description && (
        <section>
          <h3>This scene</h3>
          <p>{scene.description}</p>
          {scene.window && (
            <p className="faint">
              Window <code>{scene.window.start}</code> to <code>{scene.window.end}</code>
              {scene.window.half_open ? ', end exclusive.' : '.'}
            </p>
          )}
        </section>
      )}

      <section>
        <h3>What the layers are</h3>
        <p>
          Every row in the detections list is one algorithm, on one sensor, from one
          platform. Naming the source alone would hide the differences that matter: the
          DEA feed carries a VIIRS product, a MODIS-named product and two generations of
          BRIGHT on Himawari, and they are not the same observation.
        </p>
        <p>
          A row showing zero was queried and returned nothing for this window. That is not
          the same as a sensor never being consulted, so it keeps its row.
        </p>
        <p>
          Colour separates orbit: warm hues are geostationary, cool hues polar-orbiting.
          An AHI pixel is about 2 km across and a VIIRS pixel about 375 m, and seeing
          them at true scale side by side says more about the cadence and resolution
          trade than any caption could.
        </p>
      </section>

      <section>
        <h3>Footprints, not perimeters</h3>
        <p>
          Every polygon is a satellite pixel footprint. None of them is a fire perimeter.
        </p>
        <p>{CAVEATS.experimental}</p>
        <p>{CAVEATS.ambiguous}</p>
        <p>
          Because a 375 m footprint is roughly a seventh of a screen pixel at a
          state-wide view, each detection also carries a marker that hands over to the
          real polygon once it is large enough to read. <strong>Footprints</strong> mode
          forces true scale at every zoom; records that carry no geometry at all keep
          their marker, or the DEA hotspots would simply vanish.
        </p>
      </section>

      <section>
        <h3>Brightness temperature</h3>
        <p>
          Reported with the band it was measured in, because the sources do not agree on
          one. VIIRS reports I4 at 3.74 µm, MODIS reports T21 at 4 µm, BRIGHT reports the
          AHI B07 mid-infrared at 3.9 µm, and DEA reports a Kelvin value without naming a
          band. Presenting those as one unlabelled number would flatten a real difference.
        </p>
      </section>

      <section>
        <h3>Two things the source data gets odd</h3>
        <p>
          DEA reports <code>AFMOD</code> — a MODIS algorithm — against VIIRS platforms.
          That is what the service returns and it is shown unaltered rather than quietly
          corrected here.
        </p>
        <p>
          Confidence is stored twice. VIIRS Standard Processing reports <code>n</code>,
          <code>l</code> or <code>h</code>; MODIS reports a percentage. Coercing a
          category to a number would invent information, so both travel together with the
          scheme that gives them meaning.
        </p>
      </section>

      <section>
        <h3>Contextual layers</h3>
        <p>
          These describe the ground and the season, not the fire, and they always draw
          beneath every detection. Weather is current conditions rather than conditions at
          the time of a historical scene.
        </p>
      </section>

      {sources && (
        <section>
          <h3>Sources in this scene</h3>
          {Object.entries(sources).map(([name, info]) => (
            <p key={name} className="faint">
              <code>{name}</code> — {info.available
                ? `${info.count ?? 0} records`
                : `unavailable${info.reason ? `, ${info.reason}` : ''}`}
              {info.used_fixture && ', served from a committed fixture'}
              {info.truncated && ', truncated at the service cap'}
              {/* Booleans, not lengths: a bare `array.length &&` renders the 0. */}
              {Boolean(info.products_queried?.length && info.products_queried[0] !== '*')
                && ` · queried ${info.products_queried.join(', ')}`}
            </p>
          ))}
        </section>
      )}
    </Sheet>
  );
}
