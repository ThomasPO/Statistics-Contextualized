import requests
import pandas as pd
from prefect import task, Flow, Parameter
from zipfile import ZipFile
from io import BytesIO
import pysftp

# Constants
PUSH_TO_PREFECT_CLOUD_DASHBOARD = False
FTP_HOST = 'FTP_HOST'
FTP_USERNAME = 'FTP_USERNAME'
FTP_PASSWORD = 'FTP_PASSWORD'

types_var_mod = {"COD_VAR": str, "LIB_VAR": str, "COD_MOD": str, "LIB_MOD": str, "TYPE_VAR": str, "LONG_VAR": int}


@task
def extract_french_data(url, types={}, facilities_filter=()):
    """
    Extracts the French data about geolocalized facilities.

    Parameters
    ----------
    url : str
        URL of the data file
    types : dict
        List of names and intended data types of the variables to select
    facilities_filter : list
        List of types of facilities selected

    Returns
    -------
    DataFrame
        The data extracted
    """

    archive = ZipFile(BytesIO(requests.get(url).content))
    data_zip = [name for name in archive.namelist() if not name.startswith("varmod")][0]
    # if types is not specified, take all the variables
    if not types:
        # 'dtype=types' is not used here because of 'NA' values
        bpe_data = pd.read_csv(archive.open(data_zip), sep=";")
    else:
        bpe_data = pd.read_csv(archive.open(data_zip), sep=";", usecols=types.keys())
    # if facilities_filter is not empty, select only type of facilities starting with list of facility types
    if facilities_filter:
        bpe_data_filtered = bpe_data.loc[(bpe_data["TYPEQU"].str.startswith(facilities_filter))]
        return bpe_data_filtered
    return bpe_data


@task
def extract_french_metadata(url, types={}):
    """
    Extracts the French metadata about geolocalized facilities.

    Parameters
    ----------
    url : str
        URL of the metadata file
    types : dict
        List of names and intended data types of the variables to select

    Returns
    -------
    DataFrame
        The metadata extracted
    """
    archive = ZipFile(BytesIO(requests.get(url).content))
    metadata_zip = [name for name in archive.namelist() if name.startswith("varmod")][0]
    bpe_metadata = pd.read_csv(archive.open(metadata_zip), sep=";", usecols=types_var_mod.keys())
    if types:
        bpe_metadata_filtered = bpe_metadata.loc[bpe_metadata["COD_VAR"].isin(types)]
        return bpe_metadata_filtered
    return bpe_metadata


@task
def get_typ_equ(bpe_metadata):
    typ_equ = bpe_metadata.loc[(bpe_metadata["COD_VAR"] == "TYPEQU"), ["COD_MOD", "LIB_MOD"]]
    return typ_equ


@task
def write_csv_on_ftp(df):
    cnopts = pysftp.CnOpts()
    cnopts.hostkeys = None
    # TODO: Use tempfile
    csv = df.to_csv(r'gf_data_fr.csv', index=False, header=True)
    # Commented lines while waiting for details on the FTP connection
    # with pysftp.Connection(FTP_HOST, username=FTP_USERNAME, password=FTP_PASSWORD, cnopts=cnopts) as sftp:
    # with sftp.cd('files/gf/output/'):
    # sftp.put('gf_data_fr.csv')


# Build flow
def build_flow():
    with Flow("GF-EF") as flow:
        bpe_zip_url = Parameter(name="bpe_zip_url", required=True)
        types = Parameter(name="types", required=False)
        facilities_filter = Parameter(name="facilities_filter", required=False)
        french_data = extract_french_data(bpe_zip_url, types, facilities_filter)
        write_csv_on_ftp(french_data)
        french_metadata = extract_french_metadata(bpe_zip_url, types)
        typ_equ = get_typ_equ(french_metadata)
    return flow


# Run flow
if __name__ == "__main__":
    flow = build_flow()
    if PUSH_TO_PREFECT_CLOUD_DASHBOARD:
        flow.register(project_name="sample")
    else:
        # run without facilities_filter
        flow.run(parameters={
            "bpe_zip_url": "https://www.insee.fr/fr/statistiques/fichier/3568638/bpe20_sport_Loisir_xy_csv.zip",
            "types": {"AN": str, "COUVERT": str, "DEPCOM": str, "ECLAIRE": str, "LAMBERT_X": float, "LAMBERT_Y": float,
                      "NBSALLES": int, "QUALITE_XY": str, "TYPEQU": str}})
    flow.visualize()
