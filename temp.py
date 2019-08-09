
import datacube
import os
config = {
    # 'db_hostname': 'localhost',
    'db_hostname': 'agdcdev-db.nci.org.au',
    'db_port': 6432,
    'db_database': 'dg6911'
}
dc = datacube.Datacube(config=config)
# os.environ['GDAL_NETCDF_BOTTOMUP'] = 'YES'

query = {}
query['longitude'] = (146.7237, 150.6651)
query['latitude'] = (-34.6732, -36.2835)
query['crs'] = 'EPSG:4326'
#query['resolution'] = (-12500, 12500)
#query['output_crs'] = 'EPSG:3577'
query['resampling'] = 'max'
accum_prcp = dc.load(product='accum_prcp',
                     time='1990-01-01T00:00:00.0000Z',
                     **query
                    )