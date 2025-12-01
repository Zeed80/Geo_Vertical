<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"    
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:msxsl="urn:schemas-microsoft-com:xslt">

<!-- (c) 2016, Trimble Inc. All rights reserved.                                               -->
<!-- Permission is hereby granted to use, copy, modify, or distribute this style sheet for any -->
<!-- purpose and without fee, provided that the above copyright notice appears in all copies   -->
<!-- and that both the copyright notice and the limited warranty and restricted rights notice  -->
<!-- below appear in all supporting documentation.                                             -->

<!-- TRIMBLE INC. PROVIDES THIS STYLE SHEET "AS IS" AND WITH ALL FAULTS.                       -->
<!-- TRIMBLE INC. SPECIFICALLY DISCLAIMS ANY IMPLIED WARRANTY OF MERCHANTABILITY               -->
<!-- OR FITNESS FOR A PARTICULAR USE. TRIMBLE INC. DOES NOT WARRANT THAT THE                   -->
<!-- OPERATION OF THIS STYLE SHEET WILL BE UNINTERRUPTED OR ERROR FREE.                        -->

<xsl:output method="html" omit-xml-declaration="no"  encoding="utf-8"/>

<!-- Set the numeric display details i.e. decimal point, thousands separator etc -->
<xsl:variable name="DecPt" select="'.'"/>    <!-- Change as appropriate for US/European -->
<xsl:variable name="GroupSep" select="','"/> <!-- Change as appropriate for US/European -->
<!-- Also change decimal-separator & grouping-separator in decimal-format below 
     as appropriate for US/European output -->
<xsl:decimal-format name="Standard" 
                    decimal-separator="."
                    grouping-separator=","
                    infinity="Infinity"
                    minus-sign="-"
                    NaN="?"
                    percent="%"
                    per-mille="&#2030;"
                    zero-digit="0" 
                    digit="#" 
                    pattern-separator=";" />

<xsl:variable name="DecPl0" select="'#0'"/>
<xsl:variable name="DecPl1" select="concat('#0', $DecPt, '0')"/>
<xsl:variable name="DecPl2" select="concat('#0', $DecPt, '00')"/>
<xsl:variable name="DecPl3" select="concat('#0', $DecPt, '000')"/>
<xsl:variable name="DecPl4" select="concat('#0', $DecPt, '0000')"/>
<xsl:variable name="DecPl5" select="concat('#0', $DecPt, '00000')"/>
<xsl:variable name="DecPl6" select="concat('#0', $DecPt, '000000')"/>
<xsl:variable name="DecPl8" select="concat('#0', $DecPt, '00000000')"/>

<xsl:variable name="fileExt" select="'htm'"/>

<xsl:key name="reducedPt-search" match="/JOBFile/Reductions/Point" use="Name"/>

<!-- User variable definitions - Appropriate fields are displayed on the       -->
<!-- Survey Controller screen to allow the user to enter specific values       -->
<!-- which can then be used within the style sheet definition to control the   -->
<!-- output data.                                                              -->
<!--                                                                           -->
<!-- All user variables must be identified by a variable element definition    -->
<!-- named starting with 'userField' (case sensitive) followed by one or more  -->
<!-- characters uniquely identifying the user variable definition.             -->
<!--                                                                           -->
<!-- The text within the 'select' field for the user variable description      -->
<!-- references the actual user variable and uses the '|' character to         -->
<!-- separate the definition details into separate fields as follows:          -->
<!-- For all user variables the first field must be the name of the user       -->
<!-- variable itself (this is case sensitive) and the second field is the      -->
<!-- prompt that will appear on the Survey Controller screen.                  -->
<!-- The third field defines the variable type - there are four possible       -->
<!-- variable types: Double, Integer, String and StringMenu.  These variable   -->
<!-- type references are not case sensitive.                                   -->
<!-- The fields that follow the variable type change according to the type of  -->
<!-- variable as follow:                                                       -->
<!-- Double and Integer: Fourth field = optional minimum value                 -->
<!--                     Fifth field = optional maximum value                  -->
<!--   These minimum and maximum values are used by the Survey Controller for  -->
<!--   entry validation.                                                       -->
<!-- String: No further fields are needed or used.                             -->
<!-- StringMenu: Fourth field = number of menu items                           -->
<!--             Remaining fields are the actual menu items - the number of    -->
<!--             items provided must equal the specified number of menu items. -->
<!--                                                                           -->
<!-- The style sheet must also define the variable itself, named according to  -->
<!-- the definition.  The value within the 'select' field will be displayed in -->
<!-- the Survey Controller as the default value for the item.                  -->


<!-- **************************************************************** -->
<!-- Set global variables from the Environment section of JobXML file -->
<!-- **************************************************************** -->
<xsl:variable name="DistUnit"   select="/JOBFile/Environment/DisplaySettings/DistanceUnits" />
<xsl:variable name="AngleUnit"  select="/JOBFile/Environment/DisplaySettings/AngleUnits" />
<xsl:variable name="CoordOrder" select="/JOBFile/Environment/DisplaySettings/CoordinateOrder" />
<xsl:variable name="TempUnit"   select="/JOBFile/Environment/DisplaySettings/TemperatureUnits" />
<xsl:variable name="PressUnit"  select="/JOBFile/Environment/DisplaySettings/PressureUnits" />
<xsl:variable name="AreaUnit"   select="/JOBFile/Environment/DisplaySettings/AreaUnits" />
<xsl:variable name="VolumeUnit" select="/JOBFile/Environment/DisplaySettings/VolumeUnits" />

<!-- Setup conversion factor for coordinate and distance values -->
<!-- Dist/coord values in JobXML file are always in metres -->
<xsl:variable name="DistConvFactor">
  <xsl:choose>
    <xsl:when test="$DistUnit='Metres'">1.0</xsl:when>
    <xsl:when test="$DistUnit='InternationalFeet'">3.280839895</xsl:when>
    <xsl:when test="$DistUnit='USSurveyFeet'">3.2808333333357</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for angular values -->
<!-- Angular values in JobXML file are always in decimal degrees -->
<xsl:variable name="AngleConvFactor">
  <xsl:choose>
    <xsl:when test="$AngleUnit='DMSDegrees'">1.0</xsl:when>
    <xsl:when test="$AngleUnit='Gons'">1.111111111111</xsl:when>
    <xsl:when test="$AngleUnit='Mils'">17.77777777777</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for area values -->
<xsl:variable name="AreaConvFactor">
  <xsl:choose>
    <xsl:when test="$AreaUnit = 'SquareMetres'">1.0</xsl:when>
    <xsl:when test="$AreaUnit = 'SquareMiles'">
      <xsl:value-of select="1.0 div 2589988.110336"/>
    </xsl:when>
    <xsl:when test="$AreaUnit = 'SquareFeet'">
      <xsl:value-of select="3.280839895 * 3.280839895"/>
    </xsl:when>
    <xsl:when test="$AreaUnit = 'SquareUSSurveyFeet'">
      <xsl:value-of select="3.2808333333357 * 3.2808333333357"/>
    </xsl:when>
    <xsl:when test="$AreaUnit = 'Acres'">
      <xsl:value-of select="1.0 div 4046.8564224"/>
    </xsl:when>
    <xsl:when test="$AreaUnit = 'Hectares'">0.0001</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for volume values -->
<xsl:variable name="VolConvFactor">
  <xsl:choose>
    <xsl:when test="$VolumeUnit = 'CubicMetres'">1.0</xsl:when>
    <xsl:when test="$VolumeUnit = 'CubicFeet'">
      <xsl:value-of select="3.280839895 * 3.280839895 * 3.280839895"/>
    </xsl:when>
    <xsl:when test="$VolumeUnit = 'CubicUSSurveyFeet'">
      <xsl:value-of select="3.2808333333357 * 3.2808333333357 * 3.2808333333357"/>
    </xsl:when>
    <xsl:when test="$VolumeUnit = 'CubicYards'">
      <xsl:value-of select="3.280839895 * 3.280839895 * 3.280839895 div 27.0"/>
    </xsl:when>
    <xsl:when test="$VolumeUnit = 'CubicUSSurveyYards'">
      <xsl:value-of select="3.2808333333357 * 3.2808333333357 * 3.2808333333357 div 27.0"/>
    </xsl:when>
    <xsl:when test="$VolumeUnit = 'AcreFeet'">
      <xsl:value-of select="1.0 div 1233.48183754752"/>
    </xsl:when>
    <xsl:when test="$VolumeUnit = 'USAcreFeet'">
      <xsl:value-of select="1.0 div 1233.4892384681"/>
    </xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup boolean variable for coordinate order -->
<xsl:variable name="NECoords">
  <xsl:choose>
    <xsl:when test="$CoordOrder='North-East-Elevation'">true</xsl:when>
    <xsl:when test="$CoordOrder='X-Y-Z'">true</xsl:when>
    <xsl:otherwise>false</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for pressure values -->
<!-- Pressure values in JobXML file are always in millibars (hPa) -->
<xsl:variable name="PressConvFactor">
  <xsl:choose>
    <xsl:when test="$PressUnit='MilliBar'">1.0</xsl:when>
    <xsl:when test="$PressUnit='InchHg'">0.029529921</xsl:when>
    <xsl:when test="$PressUnit='mmHg'">0.75006</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<xsl:variable name="product">
  <xsl:choose>
    <xsl:when test="JOBFile/@product"><xsl:value-of select="JOBFile/@product"/></xsl:when>
    <xsl:otherwise>Trimble Survey Controller</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<xsl:variable name="version">
  <xsl:choose>
    <xsl:when test="JOBFile/@productVersion"><xsl:value-of select="JOBFile/@productVersion"/></xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="format-number(JOBFile/@version div 100, $DecPl2, 'Standard')"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:variable>


<!-- **************************************************************** -->
<!-- ************************** Main Loop *************************** -->
<!-- **************************************************************** -->
<xsl:template match="/" >
  <html>
  <font face="Arial">

  <title>Volume Computation Report</title>
  <h2>Volume Computation Report</h2>

  <!-- Set the font size for use in tables -->
  <style type="text/css">
    body, table, td, th
    {
      font-size:13px;
    }
  </style>

  <head>
  </head>

  <body>
  <table border="0" width="100%" cellpadding="5">
    <tr>
      <td align="left" width="30%">Job name:</td>
      <td align="left" width="20%"><xsl:value-of select="JOBFile/@jobName"/></td>
      <td align="left" width="30%"><xsl:value-of select="$product"/> version:</td>
      <td align="left" width="20%"><xsl:value-of select="$version"/></td>
    </tr>
    <tr>
      <td align="left" width="30%">Job creation date:</td>
      <td align="left" width="20%">
        <xsl:call-template name="FormattedDate">
          <xsl:with-param name="timeStamp" select="JOBFile/@TimeStamp"/>
        </xsl:call-template>
      </td>
    </tr>
  </table>

  <xsl:if test="(JOBFile/FieldBook/JobPropertiesRecord[last()]/Reference != '') or
                (JOBFile/FieldBook/JobPropertiesRecord[last()]/Description != '')">
    <table border="0" width="100%" cellpadding="5">
      <tr>
        <td align="left" width="30%">Job reference:</td>
        <td align="left" width="70%"><xsl:value-of select="JOBFile/FieldBook/JobPropertiesRecord[last()]/Reference"/></td>
      </tr>
      <tr>
        <td align="left" width="30%">Job description:</td>
        <td align="left" width="70%"><xsl:value-of select="JOBFile/FieldBook/JobPropertiesRecord[last()]/Description"/></td>
      </tr>
    </table>
  </xsl:if>

  <xsl:call-template name="SeparatingLine"/>

  <!-- Process the VolumeRecord nodes in the FieldBook node -->
  <xsl:apply-templates select="JOBFile/FieldBook/VolumeRecord"/>

  </body>
  </font>
  </html>
</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** VolumeRecord Node Processing ***************** -->
<!-- **************************************************************** -->
<xsl:template match="VolumeRecord">

  <xsl:call-template name="OutputVolumeHeadings"/>

  <xsl:choose>
    <xsl:when test="VolumeMethod = 'SurfaceArea'">
      <xsl:call-template name="OutputSurfaceAreaTable"/>
    </xsl:when>

    <xsl:when test="AdjustedVolumeResults">
      <xsl:call-template name="OutputAdjustedVolumesTable"/>
    </xsl:when>
    
    <xsl:otherwise>
      <xsl:call-template name="OutputRawVolumesTable"/>
    </xsl:otherwise>
  </xsl:choose>

  <xsl:call-template name="OutputBulkageShrinkageValues"/>
  
  <xsl:if test="AdjustedVolumeResults">
    <xsl:call-template name="OutputRawVolumesTable"/>
  </xsl:if>

  <xsl:call-template name="OutputAreaValues"/>

  <xsl:call-template name="BlankLine"/>
  <xsl:call-template name="BlankLine"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** Output volume headings table ***************** -->
<!-- **************************************************************** -->
<xsl:template name="OutputVolumeHeadings">

  <table width="100%" border="0">
    <caption align="top"><b><font size="3"><p align="left">Volume Computation</p></font></b></caption>
    <tr>
      <th align="left" width="25%">Method</th>
      <td align="left" width="75%">
        <xsl:call-template name="VolumeMethod">
          <xsl:with-param name="method" select="VolumeMethod"/>
        </xsl:call-template>
      </td>
    </tr>

    <xsl:choose>
      <xsl:when test="VolumeMethod = 'AboveAnElevation'">
        <tr>
          <th align="left" width="25%">Surface</th>
          <td align="left" width="75%">
            <xsl:value-of select="substring(SurfaceFileName, 1, string-length(SurfaceFileName) - 4)"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="25%">Elevation</th>
          <td align="left" width="75%">
            <xsl:call-template name="DistElevValueString">
              <xsl:with-param name="value" select="ReferenceElevation"/>
            </xsl:call-template>
          </td>
        </tr>
      </xsl:when>

      <xsl:when test="VolumeMethod = 'VoidVolume'">
        <tr>
          <th align="left" width="25%">Surface</th>
          <td align="left" width="75%">
            <xsl:value-of select="substring(SurfaceFileName, 1, string-length(SurfaceFileName) - 4)"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="25%">Elevation</th>
          <td align="left" width="75%">
            <xsl:call-template name="DistElevValueString">
              <xsl:with-param name="value" select="ReferenceElevation"/>
            </xsl:call-template>
          </td>
        </tr>
      </xsl:when>

      <xsl:when test="VolumeMethod = 'SurfaceToElevation'">
        <tr>
          <th align="left" width="25%">Surface</th>
          <td align="left" width="75%">
            <xsl:value-of select="substring(SurfaceFileName, 1, string-length(SurfaceFileName) - 4)"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="25%">Elevation</th>
          <td align="left" width="75%">
            <xsl:call-template name="DistElevValueString">
              <xsl:with-param name="value" select="ReferenceElevation"/>
            </xsl:call-template>
          </td>
        </tr>
      </xsl:when>

      <xsl:when test="VolumeMethod = 'SurfaceToSurface'">
        <tr>
          <th align="left" width="25%">Initial surface</th>
          <td align="left" width="75%">
            <xsl:value-of select="substring(SurfaceFileName, 1, string-length(SurfaceFileName) - 4)"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="25%">Final surface</th>
          <td align="left" width="75%">
            <xsl:value-of select="substring(BaseSurfaceFileName, 1, string-length(BaseSurfaceFileName) - 4)"/>
          </td>
        </tr>
      </xsl:when>

      <xsl:when test="VolumeMethod = 'StockpileDepression'">
        <tr>
          <th align="left" width="25%">Surface</th>
          <td align="left" width="75%">
            <xsl:value-of select="substring(SurfaceFileName, 1, string-length(SurfaceFileName) - 4)"/>
          </td>
        </tr>
      </xsl:when>

      <xsl:when test="VolumeMethod = 'SurfaceArea'">
        <tr>
          <th align="left" width="25%">Surface</th>
          <td align="left" width="75%">
            <xsl:value-of select="substring(SurfaceFileName, 1, string-length(SurfaceFileName) - 4)"/>
          </td>
        </tr>
      </xsl:when>
    </xsl:choose>
  </table>
</xsl:template>


<!-- **************************************************************** -->
<!-- ********* Return the volume method as a nice string ************ -->
<!-- **************************************************************** -->
<xsl:template name="VolumeMethod">
  <xsl:param name="method"/>

  <xsl:choose>
    <xsl:when test="$method = 'AboveAnElevation'">Above an elevation</xsl:when>
    <xsl:when test="$method = 'VoidVolume'">Void volume</xsl:when>
    <xsl:when test="$method = 'SurfaceToElevation'">Surface to elevation</xsl:when>
    <xsl:when test="$method = 'SurfaceToSurface'">Surface to surface</xsl:when>
    <xsl:when test="$method = 'StockpileDepression'">Stockpile/depression</xsl:when>
    <xsl:when test="$method = 'SurfaceArea'">Surface area</xsl:when>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************** Output surface area details table *************** -->
<!-- **************************************************************** -->
<xsl:template name="OutputSurfaceAreaTable">

  <table width="100%" border="0">
    <tr>
      <th align="left" width="25%">Surface area</th>
      <td align="left" width="75%">
        <xsl:call-template name="AreaValueString">
          <xsl:with-param name="area" select="SurfaceArea"/>
        </xsl:call-template>
      </td>
    </tr>

    <xsl:if test="(string(number(SurfaceDepth)) != 'NaN') and (SurfaceDepth != 0)">
      <tr>
        <th align="left" width="25%">Depth</th>
        <td align="left" width="75%">
          <xsl:call-template name="DistElevValueString">
            <xsl:with-param name="value" select="SurfaceDepth"/>
          </xsl:call-template>
        </td>
      </tr>
    </xsl:if>

    <xsl:if test="(string(number(SurfaceAreaByDepthVolume)) != 'NaN') and (SurfaceAreaByDepthVolume != 0)">
      <tr>
        <th align="left" width="25%">Volume</th>
        <td align="left" width="75%">
          <xsl:call-template name="VolumeValueString">
            <xsl:with-param name="volume" select="SurfaceAreaByDepthVolume"/>
          </xsl:call-template>
        </td>
      </tr>
    </xsl:if>
  </table>
</xsl:template>


<!-- **************************************************************** -->
<!-- **************** Output adjusted volumes table ***************** -->
<!-- **************************************************************** -->
<xsl:template name="OutputAdjustedVolumesTable">

  <table width="100%" border="1">
    <caption align="top"><b><p align="left">Adjusted volume</p></b></caption>
    <tr>
      <xsl:choose>
        <!-- Adjusted cut and fill volumes available -->
        <xsl:when test="(string(number(AdjustedVolumeResults/CutVolume)) != 'NaN') and
                        (string(number(AdjustedVolumeResults/FillVolume)) != 'NaN')">
          <th align="left" width="25%">Adjusted cut volume</th>
          <td align="right" width="25%">
            <xsl:call-template name="VolumeValueString">
              <xsl:with-param name="volume" select="AdjustedVolumeResults/CutVolume"/>
            </xsl:call-template>
          </td>
          <th align="left" width="25%">Adjusted fill volume</th>
          <td align="right" width="25%">
            <xsl:call-template name="VolumeValueString">
              <xsl:with-param name="volume" select="AdjustedVolumeResults/FillVolume"/>
            </xsl:call-template>
          </td>
        </xsl:when>
        <!-- Only adjusted cut volume available -->
        <xsl:when test="(string(number(AdjustedVolumeResults/CutVolume)) != 'NaN') and
                        (string(number(AdjustedVolumeResults/FillVolume)) = 'NaN')">
          <th align="left" width="25%">Adjusted cut volume</th>
          <td align="right" width="25%">
            <xsl:call-template name="VolumeValueString">
              <xsl:with-param name="volume" select="AdjustedVolumeResults/CutVolume"/>
            </xsl:call-template>
          </td>
          <td colspan="2">&#160;</td>
        </xsl:when>
        <!-- Only adjusted fill volume available -->
        <xsl:when test="(string(number(AdjustedVolumeResults/CutVolume)) = 'NaN') and
                        (string(number(AdjustedVolumeResults/FillVolume)) != 'NaN')">
          <th align="left" width="25%">Adjusted fill volume</th>
          <td align="right" width="25%">
            <xsl:call-template name="VolumeValueString">
              <xsl:with-param name="volume" select="AdjustedVolumeResults/FillVolume"/>
            </xsl:call-template>
          </td>
          <td colspan="2">&#160;</td>
        </xsl:when>
      </xsl:choose>
    </tr>
    <xsl:if test="string(number(AdjustedVolumeResults/CutFillBalance)) != 'NaN'">
      <tr>
        <th align="left" width="25%">Adjusted cut/fill balance</th>
        <td align="right" width="25%">
          <xsl:call-template name="VolumeValueString">
            <xsl:with-param name="volume" select="AdjustedVolumeResults/CutFillBalance"/>
          </xsl:call-template>
        </td>
        <td colspan="2">&#160;</td>
      </tr>
    </xsl:if>
  </table>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************** Output raw volumes table ****************** -->
<!-- **************************************************************** -->
<xsl:template name="OutputRawVolumesTable">

  <table width="100%" border="1">
    <caption align="top"><b><p align="left">In situ volume</p></b></caption>
    <tr>
      <xsl:choose>
        <!-- Cut and fill volumes available -->
        <xsl:when test="(string(number(VolumeResults/CutVolume)) != 'NaN') and
                        (string(number(VolumeResults/FillVolume)) != 'NaN')">
          <th align="left" width="25%">Cut volume</th>
          <td align="right" width="25%">
            <xsl:call-template name="VolumeValueString">
              <xsl:with-param name="volume" select="VolumeResults/CutVolume"/>
            </xsl:call-template>
          </td>
          <th align="left" width="25%">Fill volume</th>
          <td align="right" width="25%">
            <xsl:call-template name="VolumeValueString">
              <xsl:with-param name="volume" select="VolumeResults/FillVolume"/>
            </xsl:call-template>
          </td>
        </xsl:when>
        <!-- Only cut volume available -->
        <xsl:when test="(string(number(VolumeResults/CutVolume)) != 'NaN') and
                        (string(number(VolumeResults/FillVolume)) = 'NaN')">
          <th align="left" width="25%">Cut volume</th>
          <td align="right" width="25%">
            <xsl:call-template name="VolumeValueString">
              <xsl:with-param name="volume" select="VolumeResults/CutVolume"/>
            </xsl:call-template>
          </td>
          <td colspan="2">&#160;</td>
        </xsl:when>
        <!-- Only fill volume available -->
        <xsl:when test="(string(number(VolumeResults/CutVolume)) = 'NaN') and
                        (string(number(VolumeResults/FillVolume)) != 'NaN')">
          <th align="left" width="25%">Fill volume</th>
          <td align="right" width="25%">
            <xsl:call-template name="VolumeValueString">
              <xsl:with-param name="volume" select="VolumeResults/FillVolume"/>
            </xsl:call-template>
          </td>
          <td colspan="2">&#160;</td>
        </xsl:when>
      </xsl:choose>
    </tr>
    <xsl:if test="string(number(VolumeResults/CutFillBalance)) != 'NaN'">
      <tr>
        <th align="left" width="25%">Cut/fill balance</th>
        <td align="right" width="25%">
          <xsl:call-template name="VolumeValueString">
            <xsl:with-param name="volume" select="VolumeResults/CutFillBalance"/>
          </xsl:call-template>
        </td>
        <td colspan="2">&#160;</td>
      </tr>
    </xsl:if>
  </table>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************ Output the bulkage and shrinkage values *********** -->
<!-- **************************************************************** -->
<xsl:template name="OutputBulkageShrinkageValues">

  <table width="100%" border="0">
    <tr>
      <xsl:choose>
        <!-- Cut and fill volumes available - report both bulkage and shrinkage values -->
        <xsl:when test="(string(number(VolumeResults/CutVolume)) != 'NaN') and
                        (string(number(VolumeResults/FillVolume)) != 'NaN')">
          <th align="left" width="25%">Haul bulkage (cut)</th>
          <td align="left" width="25%">
            <xsl:value-of select="format-number(HaulBulkagePercentage, $DecPl1, 'Standard')"/>
            <xsl:text>%</xsl:text>
          </td>
          <th align="left" width="25%">Shrinkage (fill)</th>
          <td align="left" width="25%">
            <xsl:value-of select="format-number(ShrinkagePercentage, $DecPl1, 'Standard')"/>
            <xsl:text>%</xsl:text>
          </td>
        </xsl:when>
        <!-- Only cut volume available - report only bulkage value -->
        <xsl:when test="(string(number(VolumeResults/CutVolume)) != 'NaN') and
                        (string(number(VolumeResults/FillVolume)) = 'NaN')">
          <th align="left" width="25%">Haul bulkage (cut)</th>
          <td align="left" width="25%">
            <xsl:value-of select="format-number(HaulBulkagePercentage, $DecPl1, 'Standard')"/>
            <xsl:text>%</xsl:text>
          </td>
          <td colspan="2">&#160;</td>
        </xsl:when>
        <!-- Only fill volume available - report only shrinkage value -->
        <xsl:when test="(string(number(VolumeResults/CutVolume)) = 'NaN') and
                        (string(number(VolumeResults/FillVolume)) != 'NaN')">
          <th align="left" width="25%">Shrinkage (fill)</th>
          <td align="left" width="25%">
            <xsl:value-of select="format-number(ShrinkagePercentage, $DecPl1, 'Standard')"/>
            <xsl:text>%</xsl:text>
          </td>
          <td colspan="2">&#160;</td>
        </xsl:when>
      </xsl:choose>
    </tr>
  </table>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************** Output the area values ******************** -->
<!-- **************************************************************** -->
<xsl:template name="OutputAreaValues">

  <table width="100%" border="0">
    <tr>
      <xsl:choose>
        <!-- Cut and fill areas both available -->
        <xsl:when test="(string(number(CutArea)) != 'NaN') and
                        (string(number(FillArea)) != 'NaN')">
          <th align="left" width="25%">Cut area</th>
          <td align="left" width="25%">
            <xsl:call-template name="AreaValueString">
              <xsl:with-param name="area" select="CutArea"/>
            </xsl:call-template>
          </td>
          <th align="left" width="25%">Fill area</th>
          <td align="left" width="25%">
            <xsl:call-template name="AreaValueString">
              <xsl:with-param name="area" select="FillArea"/>
            </xsl:call-template>
          </td>
        </xsl:when>
        <!-- Only cut area available -->
        <xsl:when test="(string(number(CutArea)) != 'NaN') and
                        (string(number(FillArea)) = 'NaN')">
          <th align="left" width="25%">Cut area</th>
          <td align="left" width="25%">
            <xsl:call-template name="AreaValueString">
              <xsl:with-param name="area" select="CutArea"/>
            </xsl:call-template>
          </td>
          <td colspan="2">&#160;</td>
        </xsl:when>
        <!-- Only fill area available -->
        <xsl:when test="(string(number(CutArea)) = 'NaN') and
                        (string(number(FillArea)) != 'NaN')">
          <th align="left" width="25%">Fill area</th>
          <td align="left" width="25%">
            <xsl:call-template name="AreaValueString">
              <xsl:with-param name="area" select="FillArea"/>
            </xsl:call-template>
          </td>
          <td colspan="2">&#160;</td>
        </xsl:when>
      </xsl:choose>
    </tr>
  </table>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************ Return a volume value string with units *********** -->
<!-- **************************************************************** -->
<xsl:template name="VolumeValueString">
  <xsl:param name="volume"/>

  <xsl:variable name="volumeVal" select="$volume * $VolConvFactor"/>

  <xsl:choose>
    <xsl:when test="$VolumeUnit = 'CubicMetres'">
      <xsl:value-of select="format-number($volumeVal, $DecPl2, 'Standard')"/>
      <xsl:text>m&#0179;</xsl:text>
    </xsl:when>
    <xsl:when test="$VolumeUnit = 'CubicFeet'">
      <xsl:value-of select="format-number($volumeVal, $DecPl2, 'Standard')"/>
      <xsl:text>ft&#0179;</xsl:text>
    </xsl:when>
    <xsl:when test="$VolumeUnit = 'CubicUSSurveyFeet'">
      <xsl:value-of select="format-number($volumeVal, $DecPl2, 'Standard')"/>
      <xsl:text>sft&#0179;</xsl:text>
    </xsl:when>
    <xsl:when test="$VolumeUnit = 'CubicYards'">
      <xsl:value-of select="format-number($volumeVal, $DecPl2, 'Standard')"/>
      <xsl:text>yds&#0179;</xsl:text>
    </xsl:when>
    <xsl:when test="$VolumeUnit = 'CubicUSSurveyYards'">
      <xsl:value-of select="format-number($volumeVal, $DecPl4, 'Standard')"/>
      <xsl:text>yds&#0179;</xsl:text>
    </xsl:when>
    <xsl:when test="$VolumeUnit = 'AcreFeet'">
      <xsl:value-of select="format-number($volumeVal, $DecPl4, 'Standard')"/>
      <xsl:text>ac-ft</xsl:text>
    </xsl:when>
    <xsl:when test="$VolumeUnit = 'USAcreFeet'">
      <xsl:value-of select="format-number($volumeVal, $DecPl4, 'Standard')"/>
      <xsl:text>USac-ft</xsl:text>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="format-number($volumeVal, $DecPl2, 'Standard')"/>
      <xsl:text>m&#0179;</xsl:text>
    </xsl:otherwise>
  </xsl:choose>

</xsl:template>


<!-- **************************************************************** -->
<!-- ************* Return an area value string with units *********** -->
<!-- **************************************************************** -->
<xsl:template name="AreaValueString">
  <xsl:param name="area"/>

  <xsl:variable name="areaVal" select="$area * $AreaConvFactor"/>

  <xsl:choose>
    <xsl:when test="$AreaUnit = 'SquareMetres'">
      <xsl:value-of select="format-number($areaVal, $DecPl2, 'Standard')"/>
      <xsl:text>m&#0178;</xsl:text>
    </xsl:when>
    <xsl:when test="$AreaUnit = 'SquareMiles'">
      <xsl:value-of select="format-number($areaVal, $DecPl5, 'Standard')"/>
      <xsl:text>mi&#0178;</xsl:text>
    </xsl:when>
    <xsl:when test="$AreaUnit = 'SquareFeet'">
      <xsl:value-of select="format-number($areaVal, $DecPl2, 'Standard')"/>
      <xsl:text>ft&#0178;</xsl:text>
    </xsl:when>
    <xsl:when test="$AreaUnit = 'SquareUSSurveyFeet'">
      <xsl:value-of select="format-number($areaVal, $DecPl2, 'Standard')"/>
      <xsl:text>sft&#0178;</xsl:text>
    </xsl:when>
    <xsl:when test="$AreaUnit = 'Acres'">
      <xsl:value-of select="format-number($areaVal, $DecPl4, 'Standard')"/>
      <xsl:text>A</xsl:text>
    </xsl:when>
    <xsl:when test="$AreaUnit = 'Hectares'">
      <xsl:value-of select="format-number($areaVal, $DecPl4, 'Standard')"/>
      <xsl:text>Ha</xsl:text>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="format-number($areaVal, $DecPl2, 'Standard')"/>
      <xsl:text>m&#0178;</xsl:text>
    </xsl:otherwise>
  </xsl:choose>

</xsl:template>


<!-- **************************************************************** -->
<!-- ***** Return a distance/elevation value string with units ****** -->
<!-- **************************************************************** -->
<xsl:template name="DistElevValueString">
  <xsl:param name="value"/>

  <xsl:variable name="val" select="$value * $DistConvFactor"/>

  <xsl:choose>
    <xsl:when test="$DistUnit = 'Metres'">
      <xsl:value-of select="format-number($val, $DecPl3, 'Standard')"/>
      <xsl:text>m</xsl:text>
    </xsl:when>
    <xsl:when test="$DistUnit = 'InternationalFeet'">
      <xsl:value-of select="format-number($val, $DecPl3, 'Standard')"/>
      <xsl:text>ift</xsl:text>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="format-number($val, $DecPl3, 'Standard')"/>
      <xsl:text>sft</xsl:text>
    </xsl:otherwise>
  </xsl:choose>

</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** Return Formatted Date String ***************** -->
<!-- **************************************************************** -->
<xsl:template name="FormattedDate">
  <xsl:param name="timeStamp"/>
  
  <xsl:variable name="date" select="substring($timeStamp, 9, 2)"/>
  
  <xsl:variable name="month">
    <xsl:variable name="monthNbr" select="substring($timeStamp, 6, 2)"/>
    <xsl:choose>
      <xsl:when test="number($monthNbr) = 1">Jan</xsl:when>
      <xsl:when test="number($monthNbr) = 2">Feb</xsl:when>
      <xsl:when test="number($monthNbr) = 3">Mar</xsl:when>
      <xsl:when test="number($monthNbr) = 4">Apr</xsl:when>
      <xsl:when test="number($monthNbr) = 5">May</xsl:when>
      <xsl:when test="number($monthNbr) = 6">Jun</xsl:when>
      <xsl:when test="number($monthNbr) = 7">Jul</xsl:when>
      <xsl:when test="number($monthNbr) = 8">Aug</xsl:when>
      <xsl:when test="number($monthNbr) = 9">Sep</xsl:when>
      <xsl:when test="number($monthNbr) = 10">Oct</xsl:when>
      <xsl:when test="number($monthNbr) = 11">Nov</xsl:when>
      <xsl:when test="number($monthNbr) = 12">Dec</xsl:when>
    </xsl:choose>
  </xsl:variable>
  
  <xsl:value-of select="concat($date, ' ', $month, ' ', substring($timeStamp, 1, 4))"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ****************** Separating Line Output ********************** -->
<!-- **************************************************************** -->
<xsl:template name="SeparatingLine">
  <hr/>
</xsl:template>


<!-- **************************************************************** -->
<!-- *********************** Blank Line Output ********************** -->
<!-- **************************************************************** -->
<xsl:template name="BlankLine">
  <br/>
</xsl:template>


</xsl:stylesheet>