import base64
import time
from analysis import analyzeDataset, getObjsPerImg, getProportion, coco
from io import BytesIO
import dash
import dash_bootstrap_components as dbc
import dash_core_components as dcc
import dash_html_components as html
import dash_table
import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pandas_profiling import ProfileReport
from dash.dependencies import Input, Output, State, ALL
from skimage import io
from tqdm import tqdm

external_stylesheets = ["https://codepen.io/chriddyp/pen/bWLwgP.css"]
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.LUX])
analysis_df = pd.DataFrame()
anomaly_table_df = pd.DataFrame(columns=["Category", "Image filename"])
profile = ""
objCat = ""
areaCat = ""
datadir = ""
annotation_file = ""
cocoData = None


def parse_contents(contents):
    global analysis_df, datadir, annotation_file, cocoData, profile
    content_type, content_string = contents.split(",")
    if content_type == "data:application/json;base64":
        decoded = base64.b64decode(content_string).decode("UTF-8")
        with open("./output/output.json", "w") as file:
            file.write(decoded)
        annotation_file = "./output/output.json"
        cocoData = coco.COCO(annotation_file)
    elif content_type == "data:application/octet-stream;base64":
        decoded = base64.b64decode(content_string)
        try:
            analysis_df = pd.read_pickle(BytesIO(decoded), compression=None)
            print("Loaded analysis file!")
            profile = ProfileReport(analysis_df, title="Dataset").to_html()
        except Exception as e:
            print(e)
            return html.Div(
                children="Please load a valid COCO-style annotation file.",
                style={"margin-left": "50px", "margin-top": "50px"},
            )


@app.callback(
    Output("output-ann-data-upload", "children"),
    [Input("upload-annotation-data", "contents")],
)
def upload_ann_data(contents):
    if contents is not None:
        children = parse_contents(contents)
        return children


@app.callback(
    Output("output-analysis-data-upload", "children"),
    [Input("upload-analysis-data", "contents")],
)
def upload_analysis_data(contents):
    if contents is not None:
        children = parse_contents(contents)
        return children


@app.callback(Output("output", "children"), [Input("input_data_dir", "value")])
def data_dir_input(value):
    global datadir
    datadir = value


@app.callback(Output("output1", "children"), [Input("analyze_button", "n_clicks")])
def analyze_button(n_clicks):
    global datadir, annotation_file, analysis_df, profile
    if n_clicks is not None and datadir != "" and annotation_file != "":
        try:
            analysis_df = analyzeDataset(annotation_file, datadir)
            profile = ProfileReport(analysis_df, title="Dataset").to_html()
        except Exception as e:
            print(e)
            return html.Div(
                children="Please load a valid COCO-style annotation file and define a valid folder.",
                style={"margin-left": "50px", "margin-top": "50px"},
            )


@app.callback(Output("obj_hist_out", "children"), [Input("objs_per_img", "clickData")])
def display_obj_hist(click_data):
    if click_data is not None:
        cat = click_data["points"][0]["x"]
        global objCat
        objCat = cat
        title = "Number of " + cat + "s in an image w/ " + cat + "s"
        _, data = getObjsPerImg([cat], cocoData)
        fig = go.Figure(
            data=[
                go.Histogram(
                    x=data["number of objs"], xbins=dict(size=1), histnorm="probability"
                )
            ]
        )
        fig.update_layout(
            clickmode="event+select", yaxis_title="probability", title=title
        )
        return html.Div(
            [
                dcc.Graph(id="objs_hist", figure=fig),
                html.Div(
                    children="Click on bin to see images (may take up to 30 seconds)"
                ),
            ]
        )


@app.callback(Output("area_hist_out", "children"), [Input("cat_areas", "clickData")])
def display_area_hist(click_data):
    if click_data is not None:
        cat = click_data["points"][0]["x"]
        global areaCat
        areaCat = cat
        title = "Percentage area of a(n) " + cat + " in an image"
        _, data = getProportion([cat], cocoData)
        fig = go.Figure(
            data=[
                go.Histogram(
                    x=data["proportion of img"],
                    xbins=dict(size=0.05),
                    histnorm="probability",
                )
            ]
        )
        fig.update_layout(
            clickmode="event+select", yaxis_title="probability", title=title
        )
        return html.Div(
            [
                dcc.Graph(id="area_hist", figure=fig),
                html.Div(
                    children="Click on bin to see images (may take up to 30 seconds)"
                ),
            ]
        )


def fig_to_uri(in_fig, close_all=True, **save_args):
    # Save a figure as a URI
    out_img = BytesIO()
    in_fig.savefig(out_img, format="png", **save_args)
    if close_all:
        in_fig.clf()
        plt.close("all")
    out_img.seek(0)  # rewind file
    encoded = base64.b64encode(out_img.read()).decode("ascii").replace("\n", "")
    return "data:image/png;base64,{}".format(encoded)


def get_html_imgs(img_ids, cat, outlying_anns=None):
    # TODO: speed-up image loading and display
    global datadir
    html_imgs = []
    cat_ids = cocoData.getCatIds(catNms=[cat])
    print("Loading images...")
    for imgID in tqdm(set(img_ids)):
        im_ann = cocoData.loadImgs(ids=imgID)[0]
        image_filename = (
            datadir + "/" + im_ann["file_name"]
        )  # replace with your own image
        i = io.imread(image_filename) / 255.0
        plt.imshow(i)
        plt.axis("off")
        if outlying_anns is None:
            ann_ids = cocoData.getAnnIds(imgIds=imgID, catIds=cat_ids, iscrowd=None)
            anns = cocoData.loadAnns(ann_ids)
        else:
            ann_ids = set(
                cocoData.getAnnIds(imgIds=imgID, catIds=cat_ids, iscrowd=None)
            )
            ann_ids = list(ann_ids.intersection(set(outlying_anns)))
            anns = cocoData.loadAnns(ann_ids)
        cocoData.showAnns(anns)
        decoded_image = fig_to_uri(plt)
        plt.close()
        html_imgs.append(
            html.Img(
                id={"type": "output_image", "index": str(imgID)},
                src=decoded_image,
                **{"data-category": cat}
            )
        )
    return html_imgs


@app.callback(Output("obj_imgs", "children"), [Input("objs_hist", "clickData")])
def display_obj_imgs(click_data):
    if click_data is not None:
        _, data = getObjsPerImg([objCat], cocoData)
        num_objs = click_data["points"][0]["x"]
        img_ids = data.loc[data["number of objs"] == num_objs]["imgID"]
        html_imgs = get_html_imgs(img_ids, objCat)
        return html.Div(html_imgs)


@app.callback(Output("area_imgs", "children"), [Input("area_hist", "clickData")])
def display_area_imgs(click_data):
    if click_data is not None:
        _, data = getProportion([areaCat], cocoData)
        data_df = pd.DataFrame(data)
        point_nums = click_data["points"][0]["pointNumbers"]
        img_ids = data_df[data_df.index.isin(point_nums)]["imgID"]
        html_imgs = get_html_imgs(img_ids, areaCat)
        return html.Div(html_imgs)


@app.callback(Output("anomaly_imgs", "children"), [Input("cat_selection", "value")])
def display_anomalies(value):
    global analysis_df
    try:
        outlier_img_ids = (
            analysis_df["images w/ abnormal objects"][
                analysis_df["category"] == value
            ].tolist()
        )[0]
        outlier_ann_ids = (
            analysis_df["abnormal objects"][analysis_df["category"] == value].tolist()
        )[0]
        html_imgs = get_html_imgs(outlier_img_ids, value, outlying_anns=outlier_ann_ids)
        return html.Div(
            children=html_imgs,
            style={
                "margin-left": "25px",
                "margin-top": "25px",
                "overflow": "scroll",
                "border": "2px black solid",
                "box-sizing": "border-box",
                "width": "600px",
                "height": "600px",
            },
        )
    except Exception as e:
        print(e)
        return html.Div(
            children="Please load a valid COCO-style annotation file.",
            style={"margin-left": "25px", "margin-top": "25px"},
        )


@app.callback(Output("loading-output-1", "children"), [Input("cat_selection", "value")])
def input_triggers_spinner(value):
    time.sleep(1)
    return


@app.callback(
    Output("anomaly_table", "children"),
    [Input({"type": "output_image", "index": ALL}, "n_clicks")],
    [
        State({"type": "output_image", "index": ALL}, "data-category"),
        State({"type": "output_image", "index": ALL}, "id"),
    ],
)
def display_anomaly_table(n_clicks, cat, id):
    global anomaly_table_df
    for i, val in enumerate(n_clicks):
        file = id[i]["index"]
        if (val is not None) and (
            not anomaly_table_df["Image filename"].str.contains(file).any()
        ):
            new_row = {"Category": cat[i], "Image filename": file}
            anomaly_table_df = anomaly_table_df.append(new_row, ignore_index=True)
    return html.Div(
        dash_table.DataTable(
            id="anomaly_datatable",
            columns=[{"name": i, "id": i} for i in anomaly_table_df.columns],
            data=anomaly_table_df.to_dict("records"),
            row_deletable=True,
            export_format="xlsx",
            export_headers="display",
        ),
        style={"margin-right": "100px"},
    )


@app.callback(
    Output("anomaly_datatable", "children"),
    [Input("anomaly_datatable", "data_previous")],
    [State("anomaly_datatable", "data")],
)
def update_anomaly_table(prev, curr):
    if prev is None:
        dash.exceptions.PreventUpdate()
    else:
        removed = list(
            set([i["Image filename"] for i in prev])
            - set([i["Image filename"] for i in curr])
        )[0]
        global anomaly_table_df
        anomaly_table_df = anomaly_table_df[
            anomaly_table_df["Image filename"] != removed
        ]


@app.callback(Output("tabs-figures", "children"), [Input("tabs", "value")])
def render_tab(tab):
    try:
        if tab == "tab-0":
            try:
                return html.Div(
                    [html.Iframe(srcDoc=profile, height=1000, width=1500)],
                    style={
                        "width": "100%",
                        "display": "flex",
                        "align-items": "center",
                        "justify-content": "center",
                    },
                )
            except Exception as e:
                print(e)
                return html.Div(
                    children="Please load a valid COCO-style annotation file.",
                    style={"margin-left": "25px", "margin-top": "25px"},
                )

        elif tab == "tab-1":
            fig = px.bar(
                analysis_df,
                x="category",
                y="number of objects",
                title="Number of Objects per Category",
            )
            fig2 = px.pie(analysis_df, values="number of objects", names="category")
            return html.Div(
                [
                    dcc.Graph(id="cat_objs_bar", figure=fig),
                    dcc.Graph(id="cat_objs_pie", figure=fig2),
                ]
            )

        elif tab == "tab-2":
            fig = px.bar(
                analysis_df,
                x="category",
                y="number of images",
                title="Number of Images per Category",
            )
            fig2 = px.pie(analysis_df, values="number of images", names="category")
            return html.Div(
                [
                    dcc.Graph(id="cat_imgs_bar", figure=fig),
                    dcc.Graph(id="cat_imgs_pie", figure=fig2),
                ]
            )

        elif tab == "tab-3":
            title = "Avg Number Of Objects per Image"
            fig = px.bar(
                analysis_df,
                x="category",
                y="avg number of objects per img",
                title=title,
            )
            fig.update_layout(clickmode="event+select")
            return html.Div(
                [
                    dcc.Graph(id="objs_per_img", figure=fig),
                    html.Div(children="Click on bin to see probability distribution"),
                    html.Div(id="obj_hist_out"),
                    html.Div(id="obj_imgs"),
                ]
            )

        elif tab == "tab-4":
            title = "Avg Proportion of Image"
            fig = px.bar(
                analysis_df, x="category", y="avg percentage of img", title=title
            )
            return html.Div(
                [
                    dcc.Graph(id="cat_areas", figure=fig),
                    html.Div(children="Click on bin to see probability distribution"),
                    html.Div(id="area_hist_out"),
                    html.Div(id="area_imgs"),
                ]
            )

        elif tab == "tab-5":
            cat_ids = cocoData.getCatIds()
            cat_dict = cocoData.loadCats(cat_ids)
            cat_nms = [d["name"] for d in cat_dict]
            options = [{"label": i, "value": i} for i in cat_nms]

            return html.Div(
                [
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.H3(
                                        children="Select a category",
                                        style={
                                            "margin-top": "25px",
                                            "margin-left": "25px",
                                        },
                                    ),
                                    dcc.Dropdown(
                                        id="cat_selection",
                                        options=options,
                                        value=cat_nms[0],
                                        style={
                                            "margin-top": "25px",
                                            "margin-left": "25px",
                                            "margin-right": "50%",
                                        },
                                    ),
                                    html.Div(id="anomaly_imgs"),
                                ],
                                width=6,
                            ),
                            dbc.Col(
                                [
                                    html.H3(
                                        children="Flagged anomalies",
                                        style={
                                            "margin-top": "25px",
                                            "margin-right": "25px",
                                        },
                                    ),
                                    html.Div(id="anomaly_table"),
                                ],
                                width=6,
                            ),
                        ]
                    )
                ]
            )

    except Exception as e:
        print(e)
        return html.Div(
            children="Please load a valid COCO-style annotation file.",
            style={"margin-left": "25px", "margin-top": "25px"},
        )


app.config["suppress_callback_exceptions"] = True
app.layout = html.Div(
    children=[
        html.H1(
            children="Viz EDA",
            style={"margin-left": "50px", "margin-top": "50px", "font-size": "75px"},
        ),
        html.Div(
            children="Exploratory data analysis for computer vision and object recognition.",
            style={"margin-left": "50px", "margin-bottom": "50px"},
        ),
        html.Hr(),
        dcc.Upload(
            id="upload-annotation-data",
            children=dbc.Button(
                "Upload JSON Annotation File", color="primary", block=True
            ),
            multiple=False,
            style={"margin-left": "10%", "margin-right": "10%"},
        ),
        html.Hr(),
        dbc.Input(
            # TODO: Fix bug with textbox margins
            id="input_data_dir",
            type="text",
            placeholder="Path to images (i.e. C:/Users/me/project/data/val2017)",
            style={"margin-left": "10%", "margin-right": "10%"},
        ),
        html.Hr(),
        dbc.Row(
            # TODO: Fix bug with button margins
            [
                dbc.Col(
                    [
                        dcc.Upload(
                            id="upload-analysis-data",
                            children=dbc.Button(
                                "Load PKL Analysis File",
                                color="primary",
                                block=True,
                                outline=True,
                            ),
                            multiple=False,
                            style={"margin-left": "20%"},
                        )
                    ],
                    width=4,
                ),
                dbc.Col(
                    [
                        dbc.Button(
                            "Analyze",
                            id="analyze_button",
                            color="primary",
                            outline=True,
                            block=True,
                            style={"margin-right": "20%"},
                        )
                    ],
                    width=4,
                ),
            ]
        ),
        html.Hr(),
        html.Div(id="output-ann-data-upload"),
        html.Div(id="output-analysis-data-upload"),
        html.Div(id="output"),
        html.Div(id="output1"),
        dcc.Tabs(
            id="tabs",
            value="tab-0",
            children=[
                dcc.Tab(label="Overview", value="tab-0"),
                dcc.Tab(label="Objects per class", value="tab-1"),
                dcc.Tab(label="Images per class", value="tab-2"),
                dcc.Tab(label="Objects per image", value="tab-3"),
                dcc.Tab(label="Proportion of object in image", value="tab-4"),
                dcc.Tab(label="Anomaly detection", value="tab-5"),
            ],
        ),
        html.Div(id="tabs-figures"),
        html.Hr(),
        dcc.Loading(
            id="loading-1", type="default", children=html.Div(id="loading-output-1")
        ),
    ]
)

if __name__ == "__main__":
    # Run on docker
    # app.run_server(host="0.0.0.0", port=8050, debug=True)

    # Run locally
    app.run_server(port=8050, debug=True)

    # Only do analysis
    # annotation_file = ""
    # datadir = ""
    # analyzeDataset(annotation_file, datadir)