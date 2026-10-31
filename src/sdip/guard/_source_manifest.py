"""The pinned commits' source, file by file: probe P25's committed manifest (OPEN_DEBTS D9).

Generated from ``prereg/P25-receipt-2026-11-01.json`` and checked against it by
``tests/unit/test_commit_attestation.py``. Each entry is the sha256 of one installed package
file, which P25 found byte-identical to the same file in the source tree at the pinned commit.
``sdip.guard.pins`` compares the installed files with it at run time, with no network
(``DECISIONS.md`` D-0126, GeoSuite D-242). Do not edit it by hand. A pin bump needs P25
re-run and this file regenerated, and until then the commit is reported as not verified.
"""

from __future__ import annotations

from typing import Final

RECEIPT: Final[str] = "prereg/P25-receipt-2026-11-01.json"
RECEIPT_SHA256: Final[str] = "5b7b34f12521850e281d290c47324c048758fa80794116318655cc9f390fa36f"

SOURCE_MANIFEST: Final[dict[str, dict[str, object]]] = {
    "multidimio": {
        "version": "1.2.1",
        "commit_sha": "76df396e545017d2a32ee25a5f98989fa37afec4",
        "files": {
            "mdio/__init__.py": (
                "a1b6c6b5521df5eb4221fb526e2c4719c900a907155b169820027c19afa21098"
            ),
            "mdio/__main__.py": (
                "9d9b8f83d711bc933f7e98285121f6d2a3840a94720a031c1a1daceb4c3a34f2"
            ),
            "mdio/api/__init__.py": (
                "e784964664a4282c4b4160164ea7f517b5bb58425656d594b4f1a4a77de1d1ec"
            ),
            "mdio/api/io.py": ("16b2e1d0a168e3b7d32525bb03ab26879592d55a4b6e398f3c802d0ccd806390"),
            "mdio/builder/__init__.py": (
                "b91c6e7cdfc3a0c55cf27af94d23f20b0899ac8d8310f771a8c930c9cd7ba505"
            ),
            "mdio/builder/dataset_builder.py": (
                "ee71c8a12bf1b06ce8a1322cf9c60a3e615ad3284ee637d94ec28ca4cbcdae76"
            ),
            "mdio/builder/formatting_html.py": (
                "1203d14623be53d65d967d4bc4934ffcc856e558ec7f7f6592a9bb0ea5e16f9d"
            ),
            "mdio/builder/schemas/__init__.py": (
                "28311251f876e3f4cba6c5836fdb6bd50e6ea3cf1d56f3592e1a54a5a90afa66"
            ),
            "mdio/builder/schemas/base.py": (
                "adaa86da01b2f6773053a5efb95fac85100f10490d3e0abf7863c8660034149b"
            ),
            "mdio/builder/schemas/chunk_grid.py": (
                "6e27b84cbe26ad7085584552639e6d7aa81cb802cda39626dd7fa0c8ba8feedd"
            ),
            "mdio/builder/schemas/compressors.py": (
                "0cb16cff74606ae2ece74ecb8b84ad3986eef9fe2a4c4b9e6eb13c51ab83df45"
            ),
            "mdio/builder/schemas/core.py": (
                "092d95c68d545d58e2f6921de8290227a03e382e021a410d802e6c6c9c2bd8ca"
            ),
            "mdio/builder/schemas/dimension.py": (
                "55602395f19c02a82e04293473ebed765d307a3b3f1fa0715a82447488e8eaf0"
            ),
            "mdio/builder/schemas/dtype.py": (
                "a709ca0579f002a82c147dc4bbd0380258af1d00cc0719b1b96601af3b679116"
            ),
            "mdio/builder/schemas/units.py": (
                "8b8c7a37f2a0e81d9b35b4968b1abe8b80b2544768027d9153628f04ceb63a22"
            ),
            "mdio/builder/schemas/v1/__init__.py": (
                "fb466e9c140e1a43354ba6e942e4870935ffd32557b919ae3f405d78e76df6fe"
            ),
            "mdio/builder/schemas/v1/dataset.py": (
                "ff1978db36f66b97bdeb1c2bc468cf54948fd546e3648a46104ef416aec09af9"
            ),
            "mdio/builder/schemas/v1/stats.py": (
                "c318bcde728e816a8b6ddc85db64273f8974d11e7ad11c604f51561d4648170a"
            ),
            "mdio/builder/schemas/v1/units.py": (
                "8027ea79a9f78549b52d7ef37479873b130c05a0b22caea14554878666ec58e1"
            ),
            "mdio/builder/schemas/v1/variable.py": (
                "c24662916be13d2833898e4dea644d077551e5265c5b68fb60127f1bf8b0ed60"
            ),
            "mdio/builder/template_registry.py": (
                "134ff69302bca1e5b80e0256d4eec47a003c507acd2600a7ac9884edf5949420"
            ),
            "mdio/builder/templates/__init__.py": (
                "53abffeab6920210212510a33399c5de059e1078413b45910356141610df218f"
            ),
            "mdio/builder/templates/base.py": (
                "a7b4727fad3ac2f17d3f1e69f8b31c697a81882f9101263ed98076dd084426de"
            ),
            "mdio/builder/templates/seismic_2d_cdp.py": (
                "db544c62e48c81813466eb2d29ea00294cc71da1ec1428a25a9c59bf667dffa8"
            ),
            "mdio/builder/templates/seismic_2d_poststack.py": (
                "a78dbc5b19f913e7f26f50772bc5d51359c76e571581d94bb6e0cda9236dab9f"
            ),
            "mdio/builder/templates/seismic_2d_streamer_shot.py": (
                "b65436301fc7eede41d2597654d2dbb3fc50d219c7b82c43d1876636bc128e21"
            ),
            "mdio/builder/templates/seismic_3d_cdp.py": (
                "fb3a09ced4a1c40db6e275d1184cfafd6e4f2769f6cda8bf22607432225218c2"
            ),
            "mdio/builder/templates/seismic_3d_coca.py": (
                "b2a824f234fca8cba1ba9db3628ac48f769a03e6cec24504398cdd2c93a86328"
            ),
            "mdio/builder/templates/seismic_3d_obn.py": (
                "9546c4563771fc72f86827471843aceb7e003dbd7298dbf4badb92f7b3feb3a5"
            ),
            "mdio/builder/templates/seismic_3d_offset_tiles.py": (
                "2c9d720d466dd384134b49f499d3e50ebc2dff1263a6a0f1e27f0ef39b9a7388"
            ),
            "mdio/builder/templates/seismic_3d_poststack.py": (
                "f1dd364972d4e37e982ae2fb380101de7f12791636bdd17663450300c27dbc9f"
            ),
            "mdio/builder/templates/seismic_3d_receiver_gathers.py": (
                "13916a43d2ceae26ee7fa785685c23101875a0ec1607bfa5ab45ee0ab78dfe21"
            ),
            "mdio/builder/templates/seismic_3d_shot_receiver_line.py": (
                "5b6753f6c5aa02b563b70d4b8bd18d376238bf641eae2a2a82d340586a6f1e7a"
            ),
            "mdio/builder/templates/seismic_3d_streamer_field.py": (
                "16a3c765c11f9fae075b7b9c27ab8d9c59dd6c4d37f25162647e686111d3cd97"
            ),
            "mdio/builder/templates/seismic_3d_streamer_shot.py": (
                "24e0a2d68066ea7f9781f3d8076bd27abc4b0645904af07b3cc651b78172ed00"
            ),
            "mdio/builder/templates/types.py": (
                "7ee4a55a9beb7dd49750cfef41d4151bc178a5aa8c6049590c40249f234ed430"
            ),
            "mdio/builder/xarray_builder.py": (
                "8df9ae0a88c8af6c515996af7ad37ede3ad32ef279a77540cd7758b70f1dfd33"
            ),
            "mdio/commands/__init__.py": (
                "9051d39d7306acfd69cb7cb392f156ac3c26f8285a2654ca4a31b60347042636"
            ),
            "mdio/commands/copy.py": (
                "d9647fd8553f8f370c88036b05f130f9ebdcc05175e2c5ed7c3a8faf4621d74c"
            ),
            "mdio/commands/info.py": (
                "1da9daf7bcb27effaabded526124a2a39d5ca63e6da14648fc4ba72ec1948910"
            ),
            "mdio/commands/segy.py": (
                "3341ce0598214ee239e14aec26741d74f4e05ef5efa457cf2959646fc02a7cac"
            ),
            "mdio/constants.py": (
                "1385ae75061db5dff16b4253a44262404517733c3acfaaf76c53eb7653ccacb2"
            ),
            "mdio/converters/__init__.py": (
                "c14660256a6b2f5d8ecb6ccaf11ddfc4037b7cabf021825329c246bcbe651e7a"
            ),
            "mdio/converters/exceptions.py": (
                "46a0e97b519884abd8f5d4e0f6baaf03e26955efc5253730c5cad2615c80d857"
            ),
            "mdio/converters/mdio.py": (
                "7b12fa4f73ae224222181bbc7ba49f9c0a6c8ac26a8e9aa8bf019b5fba650bb7"
            ),
            "mdio/converters/segy.py": (
                "4b1f96c8c929ff22b4ce528433f091c36ffcd3f8a747f60a34ad649df49fa832"
            ),
            "mdio/converters/type_converter.py": (
                "74d61baf81129b94795ec603ff089a437449f28a7968baeec8b1094d10866b3c"
            ),
            "mdio/core/__init__.py": (
                "3906087230a8be2339a7bd7f70b4a84303d60c0dadb5850539de03ef08a8d1a2"
            ),
            "mdio/core/config.py": (
                "e0fa70a7c4627871b43223388fab7fb7a01019c96314b4044d5426633c397051"
            ),
            "mdio/core/dimension.py": (
                "a7c15e0ac1b8d4e7485afd51c1377cfd70aa9f22ae643338c4b19f03c9bf092d"
            ),
            "mdio/core/grid.py": (
                "11191650c2e6d62e5263e4106439bb91a0da0fc1defa6f6e502c0493150d0cd1"
            ),
            "mdio/core/indexing.py": (
                "6cc01a80375491caa409afb3b2bb766704861a1fb49f6531f1a06f18929c2896"
            ),
            "mdio/core/utils_write.py": (
                "9b293fd394f6ef7a47bc4b39c9bced9b68e7a247c0ba86ac1ca464ed2d9525de"
            ),
            "mdio/core/zarr_io.py": (
                "0e27e877e1f670678537e32cad3e1624ed6915d59050f08007aebc3a7c66a85c"
            ),
            "mdio/exceptions.py": (
                "4a21fd73e9af0197cf703058f59e2fd6eb5811092e867683b63e697f7bba00c4"
            ),
            "mdio/ingestion/__init__.py": (
                "ccb388738b28e80171f246df3fc6fa22242932b95559b6936dde3576c9f86241"
            ),
            "mdio/ingestion/coordinates.py": (
                "9b173e756467c028d318b767b7d4abb9dbc9c316b7508e9d65bd617124065842"
            ),
            "mdio/ingestion/dataset_factory.py": (
                "c5070f7579177faa3b97998400ef574f3bedeb2312cdf39ccade30deb93469a9"
            ),
            "mdio/ingestion/grid_qc.py": (
                "d18ba36ecc88a47e85f7d859ef102e8360df555a5eb81dc966aab66173023688"
            ),
            "mdio/ingestion/metadata.py": (
                "c12add0d2c09c831df074632da6c9bdecba9b3447e82a6439b9a914f04cb03c3"
            ),
            "mdio/ingestion/schema/__init__.py": (
                "9dc25b205f8638a0d5e64ada561502acc42a9f0154c408708d9f94158c902988"
            ),
            "mdio/ingestion/schema/models.py": (
                "6184047e74eeab04f5e92d7a1f50a1e9a68508b6d637c0f80a4e128b54812ea1"
            ),
            "mdio/ingestion/schema/resolver.py": (
                "a02366ac3ed59fd58d9217e925d9ee635a58aa3c69bb52d81d01c29fe9ff2ed9"
            ),
            "mdio/ingestion/segy/__init__.py": (
                "cb3327cfea591092a531c7681fa81d708f1ba0e81e73b6dbeb9b52e6e0221df2"
            ),
            "mdio/ingestion/segy/coordinates.py": (
                "6efab1bd0d4420650ab73ce2a780ccb67709783c58c33fa1d94eb9a10fd1c54e"
            ),
            "mdio/ingestion/segy/file_headers.py": (
                "48e2b97315ad1c8755eb98a9cc8d4eaa5a49a3066d244c577ab9883a6843f865"
            ),
            "mdio/ingestion/segy/header_analysis.py": (
                "ead5db9894acca22db558822f4b924f0453bef45a3fb10017055340efc2d4946"
            ),
            "mdio/ingestion/segy/index_strategies.py": (
                "35fb7dbea6fe39d9d7b2cef826a8737e6e0a151fc22e3170f0bb9968be871f78"
            ),
            "mdio/ingestion/segy/pipeline.py": (
                "f286ee0d46894322c328519b2cfc6ef865beba02f9302d166d36a43b2372e9fd"
            ),
            "mdio/ingestion/segy/raw_headers.py": (
                "40f73d64b0f6a470a854bbfbd8e622f79de6eb8e415113239e3f76a460d043ae"
            ),
            "mdio/ingestion/segy/reader.py": (
                "bd93c05b66d33a35d199da3d4da6ddeebde41e806f311a4ab408a6654bdfe498"
            ),
            "mdio/ingestion/segy/schema_effects.py": (
                "f772607b6997a46b1cbc2f7e9663492b6f386d933374407904620e70d14d7ab6"
            ),
            "mdio/ingestion/segy/serializer.py": (
                "9a3aab5c037d98334d373eb8ac4a42fc18e9bb378521575be9c6b2367b8be0b6"
            ),
            "mdio/ingestion/segy/validation.py": (
                "375dfb15a1c47f00a01775e922291a23765f206c5041f5ff7e835c9e3abe3d84"
            ),
            "mdio/optimize/__init__.py": (
                "3df46ea06bc405e7140879a90bef54618ff7344e6d1cbf57e1f9746a7b6abc2e"
            ),
            "mdio/optimize/access_pattern.py": (
                "4c2a6b774c9aca17656c56b7b112177ac2a17f16316514c0c97d3e6934626836"
            ),
            "mdio/optimize/common.py": (
                "e105d104535fcdddfe12eb83b82e335f1ab089594869e30ab1803ee92df5f6e2"
            ),
            "mdio/optimize/patch.py": (
                "d3e10d7e1ee0f63cd10fe651e865de4d319589b7ca3064ef1c33118f8ea1771e"
            ),
            "mdio/py.typed": ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
            "mdio/segy/__init__.py": (
                "b2c144520ab22ffabe3c976c18b8b8adf623c671d2955eb86780c9c80513897e"
            ),
            "mdio/segy/_raw_trace_wrapper.py": (
                "936d4959d9b27742cc33d85fc00f9b4ac5a9f530691c7ccc2160c7b08b523ac8"
            ),
            "mdio/segy/_workers.py": (
                "c84748123d9f30c82a19e3b67f6cc13d814d360b39e0c39bdad9a0072bb5f5d8"
            ),
            "mdio/segy/blocked_io.py": (
                "0f361bd17bc15139cca541d56249ba7c0cf80f87b49f121aa55ca4c984c4aff2"
            ),
            "mdio/segy/compat.py": (
                "f6efe75680723b781d1fe421d369a7f07481377566dddc8f6b7aca5f55d120ad"
            ),
            "mdio/segy/creation.py": (
                "40dcd4fd268af1c4cedbd1ee4de8199d1bd558766c9ee122b10a13cabfb4b5f8"
            ),
            "mdio/segy/exceptions.py": (
                "293dc280f845b907d962b2bf4e865be7061d73b1df7947b878dddca56fe06ad5"
            ),
            "mdio/segy/file.py": (
                "3d1611979c561be9395f4275e8d7edf1c661733d9d7447906c5c0f290edff7fe"
            ),
            "mdio/segy/geometry.py": (
                "af1bf5b5a5563eab40c321846ce12468b68dc6f9615001c695c3689c09eb600a"
            ),
            "mdio/segy/helpers_segy.py": (
                "aeb6f16d65cbb86efeebbcf55ec0adc27d0a377e64a80442cc62b4e8288269ea"
            ),
            "mdio/segy/parsers.py": (
                "9190eee7c0f5a72a78a1c08c3c83069323cbd793faddcc020b5b5a943d221086"
            ),
            "mdio/segy/scalar.py": (
                "d572975ef335c4a95299476676ed00afb345a222c312aeca236af46bcf316a40"
            ),
            "mdio/segy/text_header.py": (
                "1474a51e0859f8735019077498ab1d5041991ff5926d7f870aa14244ada0f076"
            ),
            "mdio/segy/utilities.py": (
                "4f1735d8859891ca31d26ab714284198f5157ca3d7a593fa8d33e7c0ff5bd1af"
            ),
        },
    },
    "segy": {
        "version": "0.6.0",
        "commit_sha": "557bceba4abce09d084a1f0b8ac466382ce5c502",
        "files": {
            "segy/__init__.py": (
                "66e14ceafc04a93dfaaa898dfbafa6dae8b3746820c98d83e5f97fdd85cf6b24"
            ),
            "segy/accessors.py": (
                "bc8d8fd69181f7220b99e18d8b9bd4c46b5f1cb8e1ad732f290b39156ceac575"
            ),
            "segy/alias/__init__.py": (
                "c5f2099ea907f23f346fc1d5cce0e69b782e0cc2b1aada7d8ed7e74c919234e3"
            ),
            "segy/alias/core.py": (
                "b85a3316af64f328778337683107169c0710d94fea05d001f9c421642aa973ee"
            ),
            "segy/alias/segyio.py": (
                "d186df4dc15419c2c8572296e35d20c07aeabc54fa585348da0aad86b768df26"
            ),
            "segy/alias/seis_unix.py": (
                "7eda8ba5e36943103d5e858295269b0ddbdff408b0d1456f3fcfaddb73452a87"
            ),
            "segy/arrays.py": ("7f3a87749efedc1aa2ff979442a4a90d7af0e89ef7d712edae222f0d31d089bf"),
            "segy/cli/__init__.py": (
                "6b52b3f7e35e5ed784d5945af08569947931a5ee64e9c81ab19614af268cc540"
            ),
            "segy/cli/common.py": (
                "7c1d71a326eaa2b0c5f503c4564e7c5db06250defd30f911d9014ac29237fb5b"
            ),
            "segy/cli/dump.py": (
                "e83994e7ffa7a914c357ea27058dee1978ee3c525bad7060e928d6b5f2d4b846"
            ),
            "segy/cli/segy.py": (
                "276f1ceb07436634cff7031051395a2a05e0974b208ab70c94c4d3147599dd43"
            ),
            "segy/config.py": ("f87e422748faaff5aeb0082c05d7bbb42fa34a0b73619f5763212f24a1203573"),
            "segy/constants.py": (
                "993f04b8a9f90743c88b439a0ab2b9545e97dedb1f6f77ca67fe5991f2ffa88a"
            ),
            "segy/ebcdic.py": ("e4b595141f452f4b97821bfc46a5f8916eef8dcc45c8ef6f160170e89022be27"),
            "segy/exceptions.py": (
                "65a2fcc94a00cb2c627d7fab8a19f2bdcf16318562fc50d46dddcc2dd7eb9ab9"
            ),
            "segy/factory.py": ("a19149f080f58c41de0e4282aa435cf7819acf9b702f946ad16f45987d601e2f"),
            "segy/file.py": ("fc4a0620cf7b24e956ea981dc9d41cb5853ff6696a4b3d01cb9bd3e259948e99"),
            "segy/ibm.py": ("19e6848683f14704950114a7094ed68d5ec5586b03f2362342aee81729eef6b4"),
            "segy/indexing.py": (
                "7447f7bce9d57b8f87a49f9db80661bd9e79223a6b1a4499f79e60a4d15000c0"
            ),
            "segy/inference.py": (
                "15e9dc5e0cbff0a8e0c819284ed84dc584304d49eb3a96d5ca7246633326082a"
            ),
            "segy/py.typed": ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
            "segy/schema/__init__.py": (
                "4da039f6117fb868efdc54ad31a40973ec9a9f96efbf0976f619e82190444aa5"
            ),
            "segy/schema/base.py": (
                "07b00352e3848c80b18a1619165fccf6c777a52a2bffc7bec0878893d63ee2c8"
            ),
            "segy/schema/format.py": (
                "df3972c5a7224cd6899179609f2b1150f41b9f31ce30501660c34b7ada63560c"
            ),
            "segy/schema/header.py": (
                "d050dd7924f4c9aa585af7df0b503522cd7b0e91a7cc813497efe7d9569daa23"
            ),
            "segy/schema/segy.py": (
                "d7134c0e3624f3f0f0df89328de108d03b27e5f408daf24cedd60e178502aff5"
            ),
            "segy/schema/text_header.py": (
                "7fb4122a3ee03b115c571c6d855b5ddec7c1709202abd4e2b49fe6df02331e62"
            ),
            "segy/schema/trace.py": (
                "48363353babc1108baf09d9c8afce35ec9beb0e9533bd426030efe0906aa71b8"
            ),
            "segy/standards/__init__.py": (
                "e10294a1dcf948dad2eb94f99b76d9d7b34648db80b3e86673536788957907ed"
            ),
            "segy/standards/codes.py": (
                "d7be2723c0a09d78b35ee44b03bc57ada363d92d53876d4d32c485fa19608159"
            ),
            "segy/standards/fields/__init__.py": (
                "b92a84c713b384dfd9681f8ca7643575aafd46cc007f1d5c8f36551e0594e8b8"
            ),
            "segy/standards/fields/base.py": (
                "f8be8f4010ad7176acef76b1baa9726da49b73097c59f206688b120ce1a194f2"
            ),
            "segy/standards/fields/binary.py": (
                "e788e0644b64ea249e1f07f3397ad70937a09a9e6016a97a2649157fa5a5d37a"
            ),
            "segy/standards/fields/trace.py": (
                "72d94ff6a796f4757e6efd84ed575b35035cfab774d95c664062d789acf4c311"
            ),
            "segy/standards/minimal.py": (
                "774219db28115f82a96385db0574e82ad0d12c93101a242d4ad5282d1a816526"
            ),
            "segy/standards/registry.py": (
                "52f245698466d184991d2841b57df670e9702ff2d2ef69024d895562388535cb"
            ),
            "segy/standards/spec.py": (
                "ad5fe5246008a68b27455ad22236dd5e5e93da9014a709ad581437db1e19e348"
            ),
            "segy/transforms.py": (
                "75306563e85b5e3a08e7c496182ac4ecb213f76d14c5ff65e032785402bb1627"
            ),
        },
    },
}
