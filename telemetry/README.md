Transferred from https://gist.github.com/ES-Alexander/1498c87ad6c07623f6776c552869c805

Extra useful within a project, rather than in a self-contained gist.

# Purpose
The code presented here is intended for programmatic use (e.g. aligning telemetry with 
other data, such as a video stream or sonar logs), or for detailed analysis where fields
are plotted against each other (e.g. to determine correlation).

If you're only interested in directly visualising your `.tlog` data (viewing trajectory
on a satellite map, and/or plotting different fields over time), you should use a dedicated
tool like [Log Viewer](https://ardupilot.org/copter/docs/common-uavlogviewer.html).

# Running Locally (on your computer)

Requires `Python >= 3.8`, and `pymavlink` and `pandas` should be installed 
(e.g. `python3 -m pip install pymavlink pandas`)

## Usage Options

### Getting available fields from telemetry file(s)
- use `--tlogs` to specify one or more `.tlog` files to analyse
- use `--list` to find fields within them
- use `--output` to specify a file to save those fields to in json format (if desired)
- prints output to terminal by default - use `--quiet` to avoid printing
```
python3 mavlogparse.py --list --output my_fields.json --tlogs "2021-10-30 17:09:56.tlog" "2021-10-30 17:40:13.tlog"
```
Edit the json file to remove any fields you're not interested in (making sure to keep the
result as valid json - don't remove closing braces, and don't leave trailing commas).

### Getting a `.csv` file from telemetry file(s)
- use `--tlogs` to specify one or more `.tlog` files to analyse
- use `--fields` to specify a json file of fields (see above for how to get one)
   - can leave off if you just want to use the defaults (`heading` (compass), `alt`
     (depth), and `climb`; 3D vibration, acceleration, and gyro; `roll`, `pitch`, and
     `yaw` (including speed for each); `temperature` (external)
- use `--output` to specify one file to save all the `csv` data to
   - can leave off if the default behaviour of one csv per `.tlog` is preferred
   - generated csv(s) intended for automatic parsing/processing, so timestamp is left in UTC
     "seconds since UNIX epoch" format
- use `--quiet` to avoid printing status updates (which file is being processed, and where
  the results are being saved)
```
python3 mavlogparse.py --fields my_fields.json --output "2021-10-30_combined.csv" \
 --tlogs "2021-10-30 17:09:56.tlog" "2021-10-30 17:40:13.tlog"
```

### Getting a `pandas.DataFrame` from a `.csv` file
- Requires `pandas` to be installed (e.g. `python3 -m pip install pandas`)
- Uses `pytz` timezones, which can be either relative to GMT/UTC (e.g. `'Etc/GMT+3'` or
  `'Etc/GMT-4'`) or based on 
  [Location](https://gist.github.com/heyalexej/8bf688fd67d7199be4a1682b3eec7568)
  (e.g. `'US/Eastern'`, `'Asia/Tokyo'`, etc - defaults to `Australia/Melbourne`)
- Timezone handling automatically deals with things like daylight savings and leap years,
  so is quite useful
```python
from mavlogparse import Telemetry

df = Telemetry.csv_to_df('2021-10-30_combined.csv', timezone='US/Eastern')
```

### Basic Plotting with Matplotlib
- Requires `matplotlib` to be installed (e.g. `python3 -m pip install matplotlib`)
```python
import matplotlib.pyplot as plt
from mavlogparse import Telemetry

df = Telemetry.csv_to_df('2021-10-30_combined.csv')
#df.plot() # literally everything over time (almost always a bad idea)
df['VFR_HUD.alt'].plot() # depth over time
... # configure as desired
plt.show() # display the plot (blocking - close plot to continue, or use `plt.show(block=False)` instead)

# plot the IMU's measured rotation speed about the x-axis, and the rollspeed determined by the Kalman Filter
df['SCALED_IMU2.xgyro'] /= 1000 # convert mrad/s -> rad/s for direct comparison
df[['SCALED_IMU2.xgyro', 'ATTITUDE.rollspeed']].plot()
plt.yabel('rad/s')
plt.show()

# plot depth against temperature
plt.scatter(df['VFR_HUD.alt'], df['SCALED_PRESSURE2.temperature'] / 100)
plt.xlabel('depth [m]')
plt.ylabel('temperature [deg C]')
plt.show()

# plot depth over time, coloured by heading (see which direction each dive was facing)
plt.scatter(df.index, df['VFR_HUD.alt'], cmap='hsv', c=df['VFR_HUD.heading'].fillna(0), s=1)
cbar = plt.colorbar(ticks=[0,90,170,270,359])
cbar.ax.set_yticklabels(['N','E','S','W','N'])
plt.show()
```

### Basic Plotting with Plotly
- Requires plotly to be installed (e.g. `python3 -m pip install plotly`)
- More interactive than matplotlib
   - Easier to compare variables (separate y-axes can easily be moved relative to each other)
- Runs in the browser
   - Can `right-click/Save As` to save the page as html, which means the interactive
     plot can be saved and sent to others
```python
import plotly.express as px
from mavlogparse import Telemetry

df = Telemetry.csv_to_df('2021-10-30_combined.csv')
fig = px.scatter(df, x='VFR_HUD.alt', y='SCALED_PRESSURE2.temperature')
fig.show()
```
